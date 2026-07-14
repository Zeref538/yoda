"""The key invariant: nothing PII-bearing survives the redactor, and the
profile (the only artifact the LLM ever sees) contains no raw seeded values."""

import json

import pandas as pd

from yoda.profiler import profile
from yoda.redactor import redact, redact_sample

PII_FIXTURE = pd.DataFrame({
    "customer_id": [1, 2, 3],
    "full_name": ["Juan Dela Cruz", "Maria Clara Santos", "Jose Rizal"],
    "email": ["juandc@gmail.com", "maria.santos@yahoo.com", "jrizal@up.edu.ph"],
    "phone": ["+639171234821", "09285554821", "63-917-555-1234"],
    "city": ["Manila", "Cebu City", "Quezon City"],
})

RAW_SECRETS = [
    "juandc@gmail.com", "maria.santos@yahoo.com", "jrizal@up.edu.ph",
    "+639171234821", "09285554821", "63-917-555-1234",
    "Juan Dela Cruz", "Maria Clara Santos", "Jose Rizal",
    "9171234821", "9285554821",
]


def test_redact_email():
    assert "juandc@gmail.com" not in redact("contact juandc@gmail.com now")


def test_redact_phone():
    for phone in ["09171234821", "+639171234821", "63-917-123-4821", "0917 123 4821"]:
        assert "1234821" not in redact(phone).replace("*", ""), phone


def test_redact_names():
    assert redact("Juan Dela Cruz") == "J*** D*** C***"


def test_sensitive_columns_fully_masked():
    s = redact_sample("Juan Dela Cruz", "full_name")
    assert "Juan" not in s and "Cruz" not in s


def test_profile_contains_no_raw_pii():
    """Serialize the whole profile; assert no seeded secret appears anywhere."""
    blob = json.dumps(profile(PII_FIXTURE), default=str)
    for secret in RAW_SECRETS:
        assert secret not in blob, f"PII leaked into profile: {secret}"
