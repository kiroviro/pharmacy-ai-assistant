# Performance Analysis - February 2026

## Summary

**Average Response Time**: 7.5s
**p99 Response Time**: ~51s (27 queries >15s out of 352)
**Target**: p99 < 10s

## Slow Query Analysis

27 queries (7.7%) took >15 seconds. Top 10 slowest:

| Time | Query |
|------|-------|
| 51.1s | Какво да взема при афти? |
| 50.3s | Мога ли да пия алкохол, докато приемам антибиотик? |
| 49.4s | Може ли дете да приема мелатонин? |
| 47.9s | Какво препоръчвате при липса на апетит? |
| 47.1s | Какво да приема при дефицит на желязо? |
| 43.9s | Какво е подходящо при стомашни киселини? |
| 43.3s | Може ли бебе да приема витамин D? |
| 42.9s | Какво препоръчвате при алергия към полени? |
| 40.5s | Какво да използвам при подсичане? |
| 39.4s | Чувствам се уморен и ми се вие свят |

## Pattern Analysis

Slow queries fall into categories:
1. **Medication interactions** (alcohol + antibiotics)
2. **Age-specific questions** (children, babies)
3. **Nutritional deficiencies** (iron, appetite)
4. **Complex/rare conditions** (mouth ulcers, dizziness)

## Likely Bottlenecks

### 1. Medical Model Inference (MedGemma 4B)
- **Cache Miss Rate**: These queries likely aren't cached
- **Token Generation**: Complex medical reasoning requires more tokens
- **Model Size**: 4B parameters on MLX (Apple Silicon)

### 2. Product Search
- **Vector DB Lookup**: May be slower for rare conditions
- **Product Refinement**: LLM reranking step

### 3. Translation
- **EN↔BG Translation**: Medical terminology translation overhead

## Optimization Strategies

### Quick Wins (Days)
1. **Increase Cache Size**: 500 → 2000 entries (covers more edge cases)
2. **Reduce max_tokens**: 500 → 300 for faster generation
3. **Timeout Guards**: Add 30s timeout, fallback to generic response

### Medium Term (Weeks)
4. **Model Quantization**: 4-bit quantization for 2x speedup
5. **Parallel Processing**: Run translation + product search in parallel
6. **Pre-compute Common Answers**: Cache top 100 FAQ responses

### Long Term (Months)
7. **Upgrade Model**: Test smaller models (1-2B) with similar accuracy
8. **Distributed Caching**: Redis for multi-pod deployments
9. **A/B Test Streaming**: Show partial responses while processing

## Monitoring Plan

Add performance tracking:
```python
# Log slow queries (>10s)
if response_time > 10:
    logger.warning(f"Slow query: {response_time}s", extra={
        "query": query,
        "category": category,
        "cache_hit": cache_hit,
    })
```

## Expected Impact

| Strategy | Expected p99 | Effort |
|----------|--------------|--------|
| Cache + max_tokens | 35s → 20s | 1 day |
| Quantization | 20s → 10s | 3 days |
| Timeouts | 10s → 10s (hard cap) | 1 day |

**Target**: Implement #1 + #3 first → p99 from 51s → 20s → 10s (hard cap)
