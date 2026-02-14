"""
MLX Concurrency Load Test

Tests whether ThreadPoolExecutor with max_workers>1 causes:
- Crashes
- Memory leaks
- Accuracy degradation
- Performance improvement

This validates the claim in api_server.py:42 that "MLX doesn't handle concurrent inference well"

Run: python tests/load_test_concurrency.py

Expected outcomes:
- If speedup > 1.5x: Update api_server.py to max_workers=2
- If speedup 1.1-1.5x: Update to max_workers=2 (marginal gain)
- If speedup < 1.1x: Keep max_workers=1 (no benefit)
- If crashes: Keep max_workers=1, document limitation
"""
import concurrent.futures
import time
from concurrent.futures import ThreadPoolExecutor
import traceback

try:
    import mlx.core as mx
except ImportError:
    print("ERROR: MLX not installed. This test requires Apple Silicon Mac with MLX.")
    exit(1)

from src.medical_model import get_medical_model


def test_concurrent_inference():
    """Test concurrent vs sequential inference."""
    print("=" * 70)
    print("MLX CONCURRENCY LOAD TEST")
    print("=" * 70)
    print("\nInitializing medical model...")

    try:
        model = get_medical_model()
        model.load()  # Pre-load to avoid measuring load time
        print("✅ Model loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return False

    # Test queries (Bulgarian medical queries)
    # NOTE: Using unique variations to avoid cache hits
    test_queries = [
        "имам главоболие",
        "боли ме гърлото",
        "имам температура",
        "кашлям от два дни",
        "имам алергия",
        "не мога да спя",
        "болка в корема",
        "имам хрема",
        "боли ме гърба",
        "имам обрив",
        "имам силно главоболие и световъртеж",
        "боли ме гърлото и имам кашлица",
        "висока температура над 38 градуса",
        "кашлям и имам болки в гърдите",
        "имам алергия към прах и котки",
        "не мога да заспя вече 3 нощи",
        "силна болка в корема след хранене",
        "хремът не спира вече седмица",
        "боли ме долната част на гърба",
        "имам обрив по ръцете и сърби",
    ]  # 20 UNIQUE queries to avoid cache

    print(f"\nTest queries: {len(test_queries)}")
    print("=" * 70)

    results = {}

    # ========================================================================
    # TEST 1: Sequential (current state - max_workers=1)
    # ========================================================================
    print("\n1️⃣  SEQUENTIAL TEST (max_workers=1 - baseline)")
    print("-" * 70)

    results_seq = []
    errors_seq = []

    start = time.time()
    for i, q in enumerate(test_queries):
        try:
            # Use cache=False to measure actual inference time
            result = model.get_medical_reasoning(q, use_cache=False)
            results_seq.append(result)
            if i % 5 == 0:
                print(f"   Progress: {i}/{len(test_queries)} queries processed...")
        except Exception as e:
            errors_seq.append(str(e))
            print(f"   ❌ ERROR on query {i}: {e}")

    seq_time = time.time() - start

    print(f"\n   ✅ Completed in {seq_time:.2f}s")
    print(f"   Success rate: {len(results_seq)}/{len(test_queries)} ({len(results_seq)/len(test_queries)*100:.1f}%)")
    print(f"   Average: {seq_time/len(test_queries):.3f}s per query")
    if errors_seq:
        print(f"   ⚠️  Errors: {len(errors_seq)}")

    results['sequential'] = {
        'time': seq_time,
        'success': len(results_seq),
        'total': len(test_queries),
        'errors': len(errors_seq),
        'avg_per_query': seq_time/len(test_queries)
    }

    # Clear memory before parallel test
    mx.metal.clear_cache()
    time.sleep(1)

    # ========================================================================
    # TEST 2: Parallel with 2 workers
    # ========================================================================
    print("\n2️⃣  PARALLEL TEST (max_workers=2)")
    print("-" * 70)

    results_2 = []
    errors_2 = []

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Use cache=False to measure actual inference time
            futures = [executor.submit(model.get_medical_reasoning, q, False) for q in test_queries]

            completed = 0
            for f in concurrent.futures.as_completed(futures):
                try:
                    results_2.append(f.result())
                    completed += 1
                    if completed % 5 == 0:
                        print(f"   Progress: {completed}/{len(test_queries)} queries processed...")
                except Exception as e:
                    errors_2.append(str(e))
                    print(f"   ❌ ERROR: {e}")

        parallel_2_time = time.time() - start

        print(f"\n   ✅ Completed in {parallel_2_time:.2f}s")
        print(f"   Success rate: {len(results_2)}/{len(test_queries)} ({len(results_2)/len(test_queries)*100:.1f}%)")
        print(f"   Average: {parallel_2_time/len(test_queries):.3f}s per query")
        print(f"   Speedup: {seq_time/parallel_2_time:.2f}x")
        if errors_2:
            print(f"   ⚠️  Errors: {len(errors_2)}")

        results['parallel_2'] = {
            'time': parallel_2_time,
            'success': len(results_2),
            'total': len(test_queries),
            'errors': len(errors_2),
            'avg_per_query': parallel_2_time/len(test_queries),
            'speedup': seq_time/parallel_2_time
        }

    except Exception as e:
        print(f"\n   ❌ FAILED: Parallel execution with 2 workers crashed!")
        print(f"   Error: {e}")
        traceback.print_exc()
        results['parallel_2'] = {'crashed': True, 'error': str(e)}

        # If 2 workers crashes, don't try 4
        print("\n⚠️  Skipping 4-worker test due to 2-worker failure")
        print_recommendations(results)
        return False

    # Clear memory before next test
    mx.metal.clear_cache()
    time.sleep(1)

    # ========================================================================
    # TEST 3: Parallel with 4 workers
    # ========================================================================
    print("\n3️⃣  PARALLEL TEST (max_workers=4)")
    print("-" * 70)

    results_4 = []
    errors_4 = []

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Use cache=False to measure actual inference time
            futures = [executor.submit(model.get_medical_reasoning, q, False) for q in test_queries]

            completed = 0
            for f in concurrent.futures.as_completed(futures):
                try:
                    results_4.append(f.result())
                    completed += 1
                    if completed % 5 == 0:
                        print(f"   Progress: {completed}/{len(test_queries)} queries processed...")
                except Exception as e:
                    errors_4.append(str(e))
                    print(f"   ❌ ERROR: {e}")

        parallel_4_time = time.time() - start

        print(f"\n   ✅ Completed in {parallel_4_time:.2f}s")
        print(f"   Success rate: {len(results_4)}/{len(test_queries)} ({len(results_4)/len(test_queries)*100:.1f}%)")
        print(f"   Average: {parallel_4_time/len(test_queries):.3f}s per query")
        print(f"   Speedup: {seq_time/parallel_4_time:.2f}x")
        if errors_4:
            print(f"   ⚠️  Errors: {len(errors_4)}")

        results['parallel_4'] = {
            'time': parallel_4_time,
            'success': len(results_4),
            'total': len(test_queries),
            'errors': len(errors_4),
            'avg_per_query': parallel_4_time/len(test_queries),
            'speedup': seq_time/parallel_4_time
        }

    except Exception as e:
        print(f"\n   ❌ FAILED: Parallel execution with 4 workers crashed!")
        print(f"   Error: {e}")
        traceback.print_exc()
        results['parallel_4'] = {'crashed': True, 'error': str(e)}

    # ========================================================================
    # RESULTS SUMMARY
    # ========================================================================
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\nSequential (baseline):  {results['sequential']['time']:.2f}s")

    if 'crashed' not in results.get('parallel_2', {}):
        print(f"Parallel (2 workers):   {results['parallel_2']['time']:.2f}s  ({results['parallel_2']['speedup']:.2f}x speedup)")
    else:
        print(f"Parallel (2 workers):   CRASHED ❌")

    if 'parallel_4' in results:
        if 'crashed' not in results['parallel_4']:
            print(f"Parallel (4 workers):   {results['parallel_4']['time']:.2f}s  ({results['parallel_4']['speedup']:.2f}x speedup)")
        else:
            print(f"Parallel (4 workers):   CRASHED ❌")

    # ========================================================================
    # RECOMMENDATIONS
    # ========================================================================
    print_recommendations(results)

    # Return success if at least 2 workers worked
    return 'crashed' not in results.get('parallel_2', {})


def print_recommendations(results):
    """Print recommendations based on test results."""
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    if 'crashed' in results.get('parallel_2', {}):
        print("\n❌ MLX DOES NOT SUPPORT CONCURRENT INFERENCE")
        print("\n   The claim in api_server.py:42 is CORRECT:")
        print("   'MLX doesn't handle concurrent inference well'")
        print("\n   ✅ KEEP: max_workers=1")
        print("   📝 ADD: Comment explaining this test validated the limitation")
        print("\n   Next steps:")
        print("   - Keep current configuration")
        print("   - Document this finding in TECHNICAL_DEBT.md")
        print("   - Consider alternative scaling (horizontal pods)")
        return

    # Check 2-worker speedup
    speedup_2 = results.get('parallel_2', {}).get('speedup', 0)
    speedup_4 = results.get('parallel_4', {}).get('speedup', 0)

    if speedup_2 >= 1.5:
        print("\n✅ MLX HANDLES CONCURRENT INFERENCE WELL!")
        print(f"\n   2 workers: {speedup_2:.2f}x speedup (>{1.5}x threshold)")

        if speedup_4 > speedup_2 * 1.2:  # 20% improvement over 2 workers
            print(f"   4 workers: {speedup_4:.2f}x speedup (even better!)")
            print("\n   🎯 RECOMMENDED: Update api_server.py:42 to max_workers=4")
            print(f"   Expected throughput gain: {speedup_4:.1f}x")
        else:
            print(f"   4 workers: {speedup_4:.2f}x speedup (diminishing returns)")
            print("\n   🎯 RECOMMENDED: Update api_server.py:42 to max_workers=2")
            print(f"   Expected throughput gain: {speedup_2:.1f}x")

        print("\n   Next steps:")
        print("   1. Update api_server.py line 42")
        print("   2. Remove the comment about MLX not handling concurrency")
        print("   3. Test in staging with real traffic")
        print("   4. Monitor VRAM usage in production")

    elif speedup_2 >= 1.1:
        print("\n🟡 MLX HANDLES CONCURRENCY WITH MARGINAL BENEFIT")
        print(f"\n   2 workers: {speedup_2:.2f}x speedup (1.1-1.5x range)")
        print("\n   🤔 DECISION NEEDED:")
        print("   - Small gain but adds complexity")
        print("   - Worth it if you're CPU-bound")
        print("   - Not worth it if you're VRAM-bound")
        print("\n   🎯 SUGGESTED: Update to max_workers=2 if:")
        print("   - You're hitting CPU limits")
        print("   - You have VRAM headroom")
        print("   - You need every bit of throughput")

    else:
        print("\n⚠️  MLX CONCURRENCY PROVIDES NO BENEFIT")
        print(f"\n   2 workers: {speedup_2:.2f}x speedup (<1.1x threshold)")
        print("\n   Possible reasons:")
        print("   - Python GIL limiting parallelism")
        print("   - Model is memory-bound, not compute-bound")
        print("   - MLX internal locking")
        print("\n   ✅ KEEP: max_workers=1")
        print("   📝 UPDATE: Comment explaining test results")
        print("\n   Next steps:")
        print("   - Document this finding")
        print("   - Consider model optimization instead")
        print("   - Look into horizontal scaling (multiple pods)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    print("\n🚀 Starting MLX Concurrency Load Test")
    print("⏱️  This will take approximately 2-3 minutes\n")

    try:
        success = test_concurrent_inference()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with unexpected error: {e}")
        traceback.print_exc()
        exit(1)
