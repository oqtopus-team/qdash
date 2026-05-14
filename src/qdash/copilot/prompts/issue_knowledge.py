"""Prompt templates for issue-derived knowledge extraction."""

ISSUE_KNOWLEDGE_EXTRACTION_PROMPT = """\
You are an expert in superconducting qubit calibration.
Analyze the following issue thread from a calibration task and extract a structured knowledge case.

Task name: {task_name}
Chip ID: {chip_id}
Qubit ID: {qid}

Issue title: {issue_title}
Issue thread:
{thread_text}

Extract a structured postmortem knowledge case in the following JSON format.
Be concise but precise. Use English for all fields.

{{
  "title": "Short descriptive title of the case",
  "severity": "critical | warning | info",
  "human_label": "CORRECT | SUSPICIOUS | MISASSIGNMENT | NO_SIGNAL | ANOMALY | empty if unknown",
  "failure_mode_labels": ["weak_signal", "ambiguous_assignment", "model_missed_issue"],
  "case_type": ["positive_example | negative_example | boundary_case | counterexample | prompt_guidance | operator_note"],
  "model_error_type": "true_positive | false_positive | true_negative | false_negative | not_applicable | empty if unknown",
  "resolution_label": "accept_heuristic | override_parameter | rerun_task | adjust_search_range | update_heuristic | update_review_policy | add_task_knowledge | ignore_known_artifact | empty if unknown",
  "symptom": "What was observed (1-3 sentences)",
  "model_prediction": "What the model/verifier predicted, if discussed",
  "human_review_decision": "What the human reviewer decided, if discussed",
  "root_cause": "Why it happened (1-3 sentences)",
  "resolution": "How it was resolved (1-3 sentences)",
  "boundary_criteria": "Criteria that make this a boundary case or counterexample, if applicable",
  "lesson_learned": ["Key takeaway 1", "Key takeaway 2"],
  "applicability": "When this case should be retrieved in future analyses",
  "counterexample": "What overly broad rule this case counters, if applicable",
  "prompt_guidance": "Prompt or checklist guidance derived from this case"
}}

Respond with ONLY the JSON object, no other text.
"""
