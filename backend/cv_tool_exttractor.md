# CV Extractor AI Tool - Advanced Intelligence Specification

## 1. Purpose
The CV Extractor converts a user-uploaded CV (PDF or DOCX) into structured career intelligence data that can be used for scoring, roadmap generation, and evidence-based feedback.

The tool must do both:
- Structured extraction
- Deep candidate understanding

## 2. High-Level Pipeline
```text
CV File (PDF/DOCX)
  -> File Validation
  -> Text Extraction
  -> Text Cleaning/Normalization
  -> LLM Structured Intelligence Extraction
  -> Skill Normalization
  -> Derived Metrics Computation
  -> JSON Validation
  -> Persist to DB
```

## 3. Input Contract
Required:
- `profile_id: number`
- `cv_file: PDF | DOCX`

Optional:
- `target_role: string | null`

## 4. File Validation Rules
- Allowed formats: `.pdf`, `.docx`
- Max file size: 5 MB (MVP)
- Reject encrypted files
- Reject empty extraction output
- Reject unsupported formats

Error mapping:
- Unsupported format -> `400`
- Corrupt file -> `400`
- Empty extracted text -> `422`

## 5. Text Extraction Layer
- PDF: `pdfplumber` (preferred), `pypdf` fallback
- DOCX: `python-docx`

Output:
- `raw_text: string`
- `page_count: number | null`

## 6. Text Cleaning Rules
Before LLM extraction:
- Remove repeated headers/footers
- Remove page numbers
- Normalize bullets and whitespace
- Normalize obvious date tokens

Output:
- `clean_text: string`

## 7. LLM Task Definition (10 Stages)
The LLM must execute these stages in order:
1. Document understanding and section normalization
2. Structured extraction
3. Person understanding
4. Personality indicators from evidence
5. Career trajectory analysis
6. CV quality analysis
7. Missing signals detection
8. Extraction self-audit
9. Extractor training insights
10. Confidence scoring (0-100)

Hard rules:
- Never hallucinate
- If uncertain, return `null`
- Extract only explicit skills
- Deduplicate all skills
- Normalize skill casing
- Return strict JSON only

## 8. Output JSON Contract (Strict)
```json
{
  "summary": "string",
  "skills": {
    "technical": ["string"],
    "frameworks": ["string"],
    "databases": ["string"],
    "devops": ["string"],
    "tools": ["string"],
    "soft_skills": ["string"]
  },
  "experience": [
    {
      "company": "string|null",
      "role": "string|null",
      "start_date": "string|null",
      "end_date": "string|null",
      "duration_months": "number|null",
      "key_responsibilities": ["string"],
      "achievements": ["string"],
      "technologies_used": ["string"],
      "leadership_indicators": ["string"],
      "ownership_signals": ["string"],
      "impact_signals": ["string"]
    }
  ],
  "projects": [
    {
      "title": "string|null",
      "description": "string|null",
      "technologies_used": ["string"],
      "metrics": ["string"],
      "github_links": ["string"],
      "portfolio_relevance": "high|medium|low|unknown"
    }
  ],
  "education": [
    {
      "institution": "string|null",
      "degree": "string|null",
      "field_of_study": "string|null",
      "start_year": "number|null",
      "end_year": "number|null",
      "academic_level": "string|null"
    }
  ],
  "certifications": ["string"],
  "career_level_estimate": "junior|mid|senior|unknown",
  "core_strengths": ["string"],
  "potential_weaknesses": ["string"],
  "personality_indicators": ["string"],
  "career_trajectory_analysis": "string",
  "cv_weaknesses": ["string"],
  "missing_signals": ["string"],
  "possible_missed_information": ["string"],
  "extractor_learning_insights": ["string"],
  "confidence_score": 0
}
```

## 9. Required Detection Logic
### Experience
For each role detect:
- leadership indicators
- ownership signals
- impact signals

Examples:
- "Led a team of 4 engineers" -> leadership indicator
- "Improved performance by 35%" -> impact signal

### Projects
Detect:
- measurable outcomes
- project technologies
- GitHub links

### Person Understanding
Infer only from evidence:
- core strengths
- skill depth
- learning ability
- career focus
- problem-solving orientation
- specialization
- growth potential

### Personality Indicators
Infer only with textual support:
- analytical
- collaborative
- leadership oriented
- self driven
- creative
- structured thinker
- research oriented

## 10. Post-Processing Normalization
After LLM response:
- Deduplicate skills across all categories
- Normalize aliases (example: `JS` -> `JavaScript`, `PostgreSQL` -> `Postgres`)
- Move misplaced skills between categories where deterministic
- Clamp `confidence_score` to `0..100`

## 11. Derived Metrics (Code Computed)
Compute programmatically:
- `total_experience_months`
- `total_projects`
- `projects_with_metrics`
- `unique_skill_count`
- `leadership_signal_count`

## 12. API Endpoint Contract
`POST /api/cv/extract/`

Request payload:
```json
{
  "profile_id": 123,
  "target_role": "Backend Django Developer"
}
```

Success response:
```json
{
  "profile_id": 123,
  "career_level_estimate": "mid",
  "confidence_score": 88,
  "structured_cv": {}
}
```

Low-confidence response:
```json
{
  "status": "low_confidence",
  "message": "CV formatting may prevent accurate extraction.",
  "confidence_score": 34
}
```

## 13. Validation and Safeguards
- Reject unknown top-level output keys
- Enforce required keys, even if values are `null` or empty arrays
- If schema invalid, retry extraction once
- If still invalid, return extraction error for manual review

## 14. Security and Privacy
- Never log full CV text in production
- Avoid storing unnecessary PII
- Support user deletion of CV and extraction records

## 15. MVP Boundary
MVP includes:
- text extraction
- strict JSON extraction
- normalization
- persistence
- derived metrics

MVP excludes:
- OCR for image PDFs
- vector database
- multi-pass advanced enrichment