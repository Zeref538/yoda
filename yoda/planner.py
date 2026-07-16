"""Planner: proposes a cleaning plan from the profile only.

Two implementations share one interface:
- RuleBasedPlanner: deterministic heuristics — the mandatory baseline.
- LLMPlanner: local model via Ollama, strict-JSON output validated against a
  JSON Schema plus semantic checks, max 3 retries, falls back to the
  rule-based plan. The prompt contains ONLY the profile (already redacted).

A plan is a list of steps:
    {"tool": "normalize_dates", "col": "birthday",
     "params": {...}, "reason": "3 date formats found"}
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import jsonschema

TOOL_NAMES = [
    "drop_duplicates", "normalize_dates", "normalize_phone", "normalize_currency",
    "standardize_categories", "fix_dtypes", "impute_missing", "flag_outliers",
    "trim_whitespace", "validate_rule", "rename_columns",
    "drop_blank_rows", "drop_blank_columns", "replace_values",
    "encode_categories", "drop_rows_where", "scale_numeric",
    "format_text", "round_numbers",
]

# Tools (or tool modes) that delete or transform data with no profile signal
# demanding it. Allowed ONLY when a human asked / approved — never proposed
# autonomously. (Recoverable regardless: the executor keeps the original df.)
INSTRUCTION_ONLY_TOOLS = {"drop_rows_where", "scale_numeric",
                          "format_text", "round_numbers"}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "enum": TOOL_NAMES},
                    "col": {"type": ["string", "null"]},
                    "params": {"type": "object"},
                    "reason": {"type": "string"},
                },
                "required": ["tool", "col", "params", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["steps"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are the planning module of YODA, a local data-cleaning agent. You receive a
statistical PROFILE of a table (metadata only — you never see raw rows) and must
propose a cleaning plan as JSON: {"steps": [...]}.

Available tools (col = column to act on, null for whole-table tools):
- drop_duplicates(col=null) — remove full-row duplicates. Use when duplicates.full_row > 0.
- rename_columns(col=null) — snake_case all column names. If used, put it FIRST and
  refer to columns by their snake_case names in later steps.
- trim_whitespace(col) — strip/collapse whitespace, unicode NFC. Use for whitespace_issues.
- normalize_dates(col) — mixed date formats -> ISO 8601. Use when date_formats_seen
  has >1 format or a non-ISO format.
- normalize_phone(col) — PH phone formats -> E.164. Use for phone_formats_seen chaos.
- normalize_currency(col) — currency strings -> float + currency column. Use for
  currency_like_values.
- standardize_categories(col) — fold casing variants to canonical. Use for casing_variants.
- fix_dtypes(col, params={"target": "numeric"|"bool"}) — coerce strings to numbers/bools.
  Use for numeric_as_string / bool_as_string.
- impute_missing(col, params={"strategy": "flag_only"}) — always use flag_only; never
  silently fill values. Use when null_pct > 0.
- flag_outliers(col, params={"method": "iqr"}) — adds a flag column. Use for iqr_outliers.
- validate_rule(col, params with min/max/allowed) — only when an obvious domain rule exists.
- drop_blank_rows(col=null) — remove rows that are entirely empty. Use when the
  profile has blank_rows > 0, or the user asks to remove blank/empty rows.
  With col set, removes rows where THAT column is empty (only if the user asks).
- drop_blank_columns(col=null) — remove columns that are entirely empty. Use when
  the profile lists blank_columns, or the user asks. With col set, drops that
  exact column (only when the user explicitly asks to delete it).
- replace_values(col, params={"find": ..., "replace": ..., "regex": bool}) —
  find/replace inside one column. Use ONLY when the user explicitly asks for a
  replacement; never invent one.
- encode_categories(col, params={"start": 1}) — label-encode: map each distinct
  value to an integer (1,2,3,4...). Use when the user asks to turn categories
  into numbers / number them by category / assign codes per unique value.
- drop_rows_where(col, params with ONE of: equals / contains / regex /
  is_null:true / min+max; plus keep:true to invert, match_case:false) — delete
  rows matching a condition (or keep only those). ONLY on an explicit user ask.
- scale_numeric(col, params={"method": "minmax"|"zscore"}) — rescale a numeric
  column to 0..1 or z-scores. ONLY on an explicit user ask.
- format_text(col, params={"case": "upper"|"lower"|"title"|"sentence"}) — unify
  text casing. ONLY on an explicit user ask.
- round_numbers(col, params={"decimals": 2}) — round numerics. ONLY on an
  explicit user ask.

Rules: propose a step ONLY when the profile shows evidence for it. Do not invent
columns. Do not clean what is not dirty — unnecessary changes are penalized.
Each step needs a short "reason" citing the profile evidence.

EXCEPTION — user instructions win. When the user gives an explicit instruction,
your job is to DO WHAT THEY ASK: satisfy it with the matching tool(s) even if the
profile shows no signal for it, and even if nothing looks "dirty". The human is
the authority. Read the instruction for INTENT, not exact keywords — different
wordings of the same request map to the same tool. If an instruction names a
column, act on that column; if it does not, pick the column its description best
fits from the profile. If truly nothing matches, return an empty plan rather than
inventing unrelated steps.

Plain-language mapping (match on meaning, these are examples not the only phrasings):
- "clean everything", "clean the whole table", "fix all the issues", "do a full
  clean" -> propose EVERY step the profile evidence supports, exactly as the
  signal -> tool rules above dictate (still flag-only for nulls/outliers).
- "remove/delete/drop blank|empty rows", "get rid of empty lines" -> drop_blank_rows
- "remove empty/blank columns" -> drop_blank_columns
- "delete/drop/remove column X", "I don't need X" -> drop_blank_columns(col=X)
- "replace A with B in X", "change A to B", "swap A for B" -> replace_values(col=X,
  params={"find":"A","replace":"B"})
- "change these to 1,2,3,4", "number them by category", "turn X into numbers",
  "give each value a code", "encode/label-encode X depending on the unique value"
  -> encode_categories(col=X)
- "remove/drop duplicates", "dedupe" -> drop_duplicates
- "fix/standardize/clean up the dates", "make dates consistent" -> normalize_dates
- "standardize/unify the categories", "make the casing consistent" -> standardize_categories
- "fill missing with the average/mean|median|mode", "fill the blanks with X"
  -> impute_missing(params={"strategy":"mean|median|mode|constant"}) — an explicit
  user ask is the ONE case where a strategy other than flag_only is allowed.
- "trim/strip the spaces", "clean up whitespace" -> trim_whitespace
- "delete/remove rows where X is Y", "drop the inactive customers", "remove rows
  with missing X" -> drop_rows_where(col=X, params={"equals": "Y"} or
  {"is_null": true}); "keep only rows where X is Y" -> add "keep": true
- "remove/delete the outliers in X" -> flag_outliers(col=X,
  params={"method":"iqr","action":"drop"}) — drop action only when asked;
  plain "flag the outliers" stays the default flag column.
- "replace every/all A with B", "change all occurrences of A to B" (inside
  cells) -> replace_values(params={"find":"A","replace":"B","contains":true});
  whole-cell replacement omits "contains".
- "normalize/scale X between 0 and 1" -> scale_numeric(col=X,
  params={"method":"minmax"}); "standardize X to z-scores" -> method "zscore"
- "make X uppercase/lowercase/title case", "capitalize the names"
  -> format_text(col=X, params={"case": ...})
- "round X to N decimals" -> round_numbers(col=X, params={"decimals": N})
- "drop/delete columns X and Y" -> drop_blank_columns(col=null,
  params={"columns": ["X","Y"]})

Tool-choice examples (learn the signal -> tool mapping exactly):
1. Profile shows: "price": {"currency_like_values": 25, "numeric_as_string": 180}
   -> {"tool": "normalize_currency", "col": "price", "params": {},
       "reason": "25 currency-style values (₱/PHP prefixes) present"}
   currency_like_values ALWAYS wins over fix_dtypes, even when
   numeric_as_string is larger: fix_dtypes cannot parse '₱1,200.00' and
   will corrupt the column. Never propose fix_dtypes on a column that has
   currency_like_values.
2. Profile shows: "qty": {"numeric_as_string": 40} and NO currency_like_values
   -> {"tool": "fix_dtypes", "col": "qty", "params": {"target": "numeric"},
       "reason": "40 plain numeric strings, no currency symbols"}
3. Profile shows: "n_rows": 130 but duplicates: {"full_row": 10}
   -> {"tool": "drop_duplicates", "col": null, "params": {},
       "reason": "10 exact duplicate rows"}
4. Profile shows: "age": {"iqr_outliers": 12, "null_pct": 4.0}
   -> TWO steps: flag_outliers(age, {"method": "iqr"}) AND
      impute_missing(age, {"strategy": "flag_only"}) — outliers and nulls
      are separate issues; both are flagged, never deleted or filled.
5. User asks: "change the department column to 1,2,3,4 depending on the value"
   -> {"tool": "encode_categories", "col": "department", "params": {},
       "reason": "user asked to label-encode categories as integers"}
   This is an explicit instruction — do it even though no profile signal
   demands it.
6. Targeted asks answer with EXACTLY the asked step, nothing else:
   "delete the note column" -> ONE step
   {"tool": "drop_blank_columns", "col": "note", "params": {}, "reason": "user asked"}
   "keep only rows where department is Sales" -> ONE step
   {"tool": "drop_rows_where", "col": "department",
    "params": {"equals": "Sales", "keep": true}, "reason": "user asked"}
   ("keep only X" ALWAYS means keep: true — dropping the non-matching rows.)
   "remove the outliers in age" -> ONE step
   {"tool": "flag_outliers", "col": "age",
    "params": {"method": "iqr", "action": "drop"}, "reason": "user asked removal"}
   (the word remove/delete means action "drop"; plain "flag" means no action)"""


class RuleBasedPlanner:
    """Baseline heuristic planner: maps profile signals to tool calls."""

    def plan(self, profile: dict) -> list[dict]:
        steps: list[dict] = []
        cols: dict = profile["columns"]

        if any(info.get("non_snake_case_name") for info in cols.values()):
            steps.append({"tool": "rename_columns", "col": None, "params": {},
                          "reason": "non-snake_case column names"})

        if profile.get("blank_rows"):
            steps.append({"tool": "drop_blank_rows", "col": None, "params": {},
                          "reason": f"{profile['blank_rows']} fully blank rows"})
        if profile.get("blank_columns"):
            steps.append({"tool": "drop_blank_columns", "col": None, "params": {},
                          "reason": f"empty columns: {profile['blank_columns']}"})

        if profile["duplicates"]["full_row"] > 0:
            steps.append({"tool": "drop_duplicates", "col": None, "params": {},
                          "reason": f"{profile['duplicates']['full_row']} full-row duplicates"})

        for name, info in cols.items():
            target = snake_case(name) if any(
                i.get("non_snake_case_name") for i in cols.values()) else name

            if info.get("whitespace_issues") or info.get("non_nfc_values"):
                steps.append({"tool": "trim_whitespace", "col": target, "params": {},
                              "reason": f"{info.get('whitespace_issues', 0)} whitespace / "
                                        f"{info.get('non_nfc_values', 0)} unicode issues"})

            fmts = info.get("date_formats_seen", {})
            if len(fmts) >= 2 or (len(fmts) == 1 and "ISO (YYYY-MM-DD)" not in fmts):
                steps.append({"tool": "normalize_dates", "col": target, "params": {},
                              "reason": f"{len(fmts)} date formats: {sorted(fmts)}"})

            pfmts = info.get("phone_formats_seen", {})
            if pfmts and set(pfmts) != {"intl (+639XXXXXXXXX)"}:
                steps.append({"tool": "normalize_phone", "col": target, "params": {},
                              "reason": f"phone formats: {sorted(pfmts)}"})

            if info.get("currency_like_values"):
                steps.append({"tool": "normalize_currency", "col": target, "params": {},
                              "reason": f"{info['currency_like_values']} currency-style values"})
            elif info.get("bool_as_string"):
                steps.append({"tool": "fix_dtypes", "col": target,
                              "params": {"target": "bool"},
                              "reason": "boolean values stored as strings"})
            elif info.get("numeric_as_string") and not info.get("phone_formats_seen") \
                    and not info.get("casing_variants"):
                steps.append({"tool": "fix_dtypes", "col": target,
                              "params": {"target": "numeric"},
                              "reason": f"{info['numeric_as_string']} numeric values as strings"})

            if info.get("casing_variants"):
                cv = info["casing_variants"]
                steps.append({"tool": "standardize_categories", "col": target, "params": {},
                              "reason": f"{cv['raw_unique']} raw variants fold to "
                                        f"{cv['folded_unique']} categories"})

            if info.get("null_pct", 0) > 0 and info.get("null_pct", 0) < 50:
                steps.append({"tool": "impute_missing", "col": target,
                              "params": {"strategy": "flag_only"},
                              "reason": f"{info['null_pct']}% nulls (flag, never silent-fill)"})

            if info.get("iqr_outliers"):
                steps.append({"tool": "flag_outliers", "col": target,
                              "params": {"method": "iqr"},
                              "reason": f"{info['iqr_outliers']} IQR outliers (flag, don't delete)"})
        return steps


def snake_case(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    s = re.sub(r"[^\w]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_").lower()


class PlanValidationError(ValueError):
    pass


def validate_plan(plan_obj: dict, profile: dict,
                  allow_impute_fill: bool = False) -> list[dict]:
    """Schema + semantic validation. Raises PlanValidationError with a
    message suitable for feeding back to the model on retry.

    `allow_impute_fill` is True only when a human gave an explicit
    instruction (or approved the plan) — the only case where impute fill
    strategies, row-deleting conditions, and value transforms
    (INSTRUCTION_ONLY_TOOLS, outlier action="drop") are permitted."""
    jsonschema.validate(plan_obj, PLAN_SCHEMA)
    steps = plan_obj["steps"]
    known = set(profile["columns"])
    known |= {snake_case(c) for c in known}

    for i, step in enumerate(steps):
        tool, col = step["tool"], step["col"]
        if not allow_impute_fill:
            if tool in INSTRUCTION_ONLY_TOOLS:
                raise PlanValidationError(
                    f"step {i}: '{tool}' is only allowed when the user "
                    "explicitly asks for it")
            if tool == "flag_outliers" and step["params"].get("action") == "drop":
                raise PlanValidationError(
                    f"step {i}: flag_outliers action='drop' is only allowed "
                    "when the user explicitly asks; default is a flag column")
        if tool == "replace_values" and "find" not in step["params"]:
            raise PlanValidationError(
                f"step {i}: replace_values requires params.find")
        if tool == "drop_rows_where" and not (
                {"equals", "contains", "regex", "is_null", "min", "max"}
                & set(step["params"])):
            raise PlanValidationError(
                f"step {i}: drop_rows_where needs one of equals/contains/"
                "regex/is_null/min/max in params")
        if tool in ("drop_duplicates", "rename_columns",
                    "drop_blank_rows", "drop_blank_columns"):
            if col is not None and col not in known:
                raise PlanValidationError(
                    f"step {i}: column '{col}' does not exist in the profile")
            for c in step["params"].get("columns", []):
                if c not in known:
                    raise PlanValidationError(
                        f"step {i}: column '{c}' does not exist in the profile")
            continue
        if col is None:
            raise PlanValidationError(f"step {i}: tool '{tool}' requires a column")
        if col not in known:
            raise PlanValidationError(
                f"step {i}: column '{col}' does not exist in the profile")
        if (tool == "impute_missing" and not allow_impute_fill
                and step["params"].get("strategy") not in (None, "flag_only")):
            raise PlanValidationError(
                f"step {i}: impute_missing must use strategy 'flag_only' "
                "(fill strategies are only allowed when the user explicitly asks)")
    return steps


class LLMPlanner:
    """Ollama-backed planner: strict JSON, validated, retried, with fallback."""

    def __init__(self, model: str = "qwen3.5:4b",
                 host: str = "http://localhost:11434",
                 max_retries: int = 3, timeout: int = 300) -> None:
        self.model = model
        self.host = host
        self.max_retries = max_retries
        self.timeout = timeout
        self.last_outcome: dict = {}  # telemetry for reports/benchmark

    def _chat(self, messages: list[dict], think: bool | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": PLAN_SCHEMA,  # Ollama structured output
            "options": {"temperature": 0.1},
        }
        if think is not None:
            # Thinking models can return empty content under structured
            # output; the interactive path disables thinking for fast,
            # reliable JSON. (Benchmark path leaves this unset.)
            payload["think"] = think
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())["message"]["content"]
        except urllib.error.HTTPError as exc:
            if think is not None and exc.code == 400:
                # Model doesn't accept the think parameter — resend without.
                payload.pop("think")
                req.data = json.dumps(payload).encode()
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read())["message"]["content"]
            raise

    def plan(self, profile: dict, instruction: str | None = None,
             col: str | None = None) -> list[dict]:
        """`instruction` is an optional user request (e.g. "make these dates
        ISO"); `col` scopes the plan to one column."""
        user = "PROFILE:\n" + json.dumps(profile, indent=1)
        if col:
            user += (f"\n\nScope: propose steps ONLY for column '{col}' "
                     "(plus drop_duplicates/rename_columns if clearly needed).")
        if instruction:
            user += f"\n\nThe user asks: {instruction}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        errors: list[str] = []
        for attempt in range(self.max_retries):
            try:
                raw = self._chat(
                    messages,
                    think=False if (instruction or col) else None)
                plan_obj = json.loads(raw)
                steps = validate_plan(plan_obj, profile,
                                      allow_impute_fill=bool(instruction))
                self.last_outcome = {"source": "llm", "attempts": attempt + 1,
                                     "errors": errors}
                return steps
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # Ollama unreachable — retrying won't help.
                errors.append(f"ollama unreachable: {exc}")
                break
            except (json.JSONDecodeError, jsonschema.ValidationError,
                    PlanValidationError, KeyError) as exc:
                msg = f"{type(exc).__name__}: {exc}"
                errors.append(msg)
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 f"Your plan was invalid: {msg}\n"
                                 "Return a corrected JSON plan."})
        fallback = RuleBasedPlanner().plan(profile)
        if col:
            fallback = [s for s in fallback if s.get("col") in (col, None)]
        self.last_outcome = {"source": "fallback_rule_based",
                             "attempts": self.max_retries, "errors": errors}
        return fallback
