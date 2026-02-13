# ViaPharma Chatbot Pipeline

## Architecture Overview

```mermaid
flowchart TB
    subgraph Input["User Input"]
        Q[/"Потребителска заявка<br/>(Bulgarian)"/]
    end

    subgraph Safety["Safety Fast-Path"]
        S1{Emergency<br/>Detection}
        S1 -->|"Emergency"| EMERGENCY[/"🚨 СПЕШНО<br/>Call 112"/]
    end

    subgraph Routing["Query Routing"]
        CAT{Catalog<br/>Query?}
        CAT -->|Yes| CATALOG["Direct Product<br/>Search"]
        INT{Medical<br/>Intent?}
        INT -->|No| REJECT[/"Non-medical<br/>rejection"/]
    end

    subgraph Processing["Medical Processing"]
        TR1["🔄 Translate<br/>BG → EN"]
        MED["🧠 MedGemma<br/>Medical Reasoning"]
        COND["Extract User<br/>Conditions"]
        SAF{Safety<br/>Check}
        SAF -->|"Red Flag"| DOCTOR[/"⚠️ Refer to<br/>Doctor"/]
    end

    subgraph Retrieval["Two-Stage Retrieval (Perplexity Pattern)"]
        VEC["📊 Vector Search<br/>ChromaDB<br/>(Top-K candidates)"]
        OTC["Filter OTC Only"]
        CONTRA["Filter by<br/>Contraindications"]
        LLM["🎯 LLM Refinement<br/>Select Best Products"]
    end

    subgraph Output["Response Generation"]
        TR2["🔄 Translate<br/>EN → BG"]
        FMT["📝 Format Response"]
        DISC["Add Disclaimers<br/>(Child/Pregnancy/Chronic)"]
        RESP[/"💬 Отговор на<br/>български"/]
    end

    Q --> S1
    S1 -->|"Safe"| CAT
    CAT -->|No| INT
    INT -->|Yes| TR1
    CATALOG --> FMT

    TR1 --> MED
    MED --> COND
    COND --> SAF
    SAF -->|"Safe"| VEC

    VEC --> OTC
    OTC --> CONTRA
    CONTRA --> LLM

    LLM --> TR2
    TR2 --> FMT
    FMT --> DISC
    DISC --> RESP

    style EMERGENCY fill:#ff6b6b,color:#fff
    style DOCTOR fill:#ffa94d,color:#fff
    style REJECT fill:#868e96,color:#fff
    style MED fill:#4dabf7,color:#fff
    style VEC fill:#69db7c,color:#fff
    style LLM fill:#da77f2,color:#fff
    style RESP fill:#38d9a9,color:#fff
```

## Component Details

### 1. Safety Fast-Path
- **Hard-coded keyword matching** for emergency symptoms
- Runs FIRST on every query (non-negotiable)
- Triggers: chest pain, can't breathe, suicide, poisoning, etc.
- Response: Immediate 112 emergency referral

### 2. Query Routing

#### Catalog Query Detection
Bypasses medical reasoning for product-only queries:
- "Какви марки слънцезащитни имате?"
- "Покажи ми витамини"
- "Търся крем за лице"

#### Intent Classification
- Rule-based + pattern matching
- Rejects non-pharmacy queries (delivery, payment, etc.)

### 3. Medical Processing

```mermaid
flowchart LR
    subgraph Translation
        BG["Bulgarian<br/>Query"] --> EN["English<br/>Query"]
    end

    subgraph MedGemma["MedGemma Analysis"]
        EN --> SYM["Symptoms"]
        EN --> CAUSE["Likely Cause"]
        EN --> TREAT["Treatment Type"]
        EN --> WARN["Warnings"]
        EN --> DOC["See Doctor?"]
    end

    subgraph Conditions["User Conditions"]
        BG --> PREG["Pregnancy"]
        BG --> CHILD["Child/Baby"]
        BG --> CHRONIC["Diabetes/Heart/etc."]
    end
```

### 4. Two-Stage Retrieval (Perplexity Pattern)

| Stage | Component | Purpose | Speed |
|-------|-----------|---------|-------|
| 1 | ChromaDB Vector Search | Get top-K candidates | ~50ms |
| 1b | OTC Filter | Remove prescription drugs | ~1ms |
| 1c | Contraindication Filter | Remove unsafe products | ~10ms |
| 2 | LLM Refinement | Pick best 2-3 matches | ~2-3s |

### 5. Response Generation

```mermaid
flowchart TB
    subgraph Translate["Translation EN→BG"]
        T1["Medical Dictionary<br/>(100+ terms)"]
        T2["Helsinki-NLP<br/>opus-mt-en-bg"]
        T3["Garbage Filtering<br/>(200+ patterns)"]
    end

    subgraph Format["Response Formatting"]
        F1["🩺 Симптоми"]
        F2["🔬 Вероятна причина"]
        F3["💊 Препоръчано лечение"]
        F4["🏠 Домашни грижи"]
        F5["⏱️ Възстановяване"]
        F6["⚠️ Кога да потърсите лекар"]
        F7["💊 Препоръчани продукти"]
    end

    subgraph Disclaimers["Conditional Disclaimers"]
        D1["👶 Pediatric Warning"]
        D2["🤰 Pregnancy Warning"]
        D3["💊 Chronic Disease Warning"]
        D4["⚠️ Safety Information"]
        D5["🚫 Contraindication Warning"]
    end

    T1 --> T2 --> T3
    T3 --> F1 --> F2 --> F3 --> F4 --> F5 --> F6 --> F7
    F7 --> D1 & D2 & D3 & D4 & D5
```

## Data Flow Summary

```
User Query (BG)
    ↓
[Emergency Check] → 🚨 Emergency Response
    ↓
[Catalog Check] → 🛒 Direct Product Listing
    ↓
[Intent Check] → ❌ Non-medical Rejection
    ↓
[Translate BG→EN]
    ↓
[MedGemma Reasoning]
    ↓
[Safety Check] → ⚠️ Doctor Referral
    ↓
[ChromaDB Search] → Top 10 candidates
    ↓
[OTC + Contraindication Filter] → Safe products
    ↓
[LLM Refinement] → Best 2-3 products
    ↓
[Translate EN→BG]
    ↓
[Format + Disclaimers]
    ↓
Final Response (BG)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/pipeline/orchestrator.py` | Main pipeline orchestrator |
| `src/pipeline/models.py` | Data models (Product, PipelineResult) |
| `src/pipeline/constants.py` | Symptom mappings, keywords |
| `src/pipeline/conditions.py` | User condition extraction |
| `src/pipeline/product_ingredients.py` | Ingredient parsing |
| `src/pipeline/query_router.py` | Query routing logic |
| `src/medical_model.py` | MedGemma integration |
| `src/translator.py` | BG↔EN translation |
| `src/product_store.py` | ChromaDB vector store |
| `src/safety.py` | Emergency/red-flag detection |
| `src/intent_classifier.py` | Medical intent detection |
| `src/unified_processor.py` | Unified LLM processor |

## Performance Metrics

| Query Type | Avg Response Time |
|------------|-------------------|
| Non-medical (rejected) | 2-3ms |
| Catalog query | 50-200ms |
| Medical query | 5-15s |
| Emergency detection | 1-2ms |
