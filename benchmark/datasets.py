"""Clean source datasets for the corruption benchmark.

All datasets are generated deterministically (seeded) and fully offline —
no downloads, matching YODA's no-internet principle. Mix mirrors CLAUDE.md:
a Titanic-style passenger table, retail orders, a PH-flavored customer table
(Faker en_PH), employees, clinic patients, and product inventory.
"""

from __future__ import annotations

import random

import pandas as pd
from faker import Faker


def _fake(seed: int, locale: str = "en_PH") -> Faker:
    f = Faker(locale)
    f.seed_instance(seed)
    return f


def titanic_style(n: int = 400, seed: int = 1) -> pd.DataFrame:
    rng = random.Random(seed)
    f = _fake(seed, "en_US")
    rows = [{
        "passenger_id": i + 1,
        "name": f.name(),
        "sex": rng.choice(["male", "female"]),
        "age": rng.randint(1, 79),
        "pclass": rng.choice([1, 2, 3]),
        "fare": round(rng.uniform(5, 260), 2),
        "embarked": rng.choice(["S", "C", "Q"]),
        "survived": rng.choice([0, 1]),
    } for i in range(n)]
    return pd.DataFrame(rows)


def retail_orders(n: int = 500, seed: int = 2) -> pd.DataFrame:
    rng = random.Random(seed)
    f = _fake(seed, "en_US")
    products = ["Laptop", "Mouse", "Keyboard", "Monitor", "Webcam", "Headset", "Dock"]
    rows = [{
        "order_id": 10000 + i,
        "order_date": f.date_between("-2y", "today").isoformat(),
        "product": rng.choice(products),
        "category": rng.choice(["Electronics", "Accessories", "Peripherals"]),
        "quantity": rng.randint(1, 8),
        "unit_price": round(rng.uniform(3, 900), 2),
        "shipped": rng.choice([True, False]),
    } for i in range(n)]
    return pd.DataFrame(rows)


def ph_customers(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = random.Random(seed)
    f = _fake(seed)
    rows = [{
        "customer_id": 5000 + i,
        "full_name": f.name(),
        "email": f.email(),
        "phone": "+639" + "".join(str(rng.randint(0, 9)) for _ in range(9)),
        "city": rng.choice(["Quezon City", "Manila", "Cebu City", "Davao City", "Makati"]),
        "signup_date": f.date_between("-3y", "today").isoformat(),
        "monthly_spend": round(rng.uniform(200, 12000), 2),
        "segment": rng.choice(["Retail", "SME", "Enterprise"]),
    } for i in range(n)]
    return pd.DataFrame(rows)


def employees(n: int = 300, seed: int = 4) -> pd.DataFrame:
    rng = random.Random(seed)
    f = _fake(seed, "en_US")
    rows = [{
        "employee_id": 900 + i,
        "name": f.name(),
        "department": rng.choice(["Engineering", "Sales", "Finance", "HR", "Support"]),
        "hire_date": f.date_between("-10y", "today").isoformat(),
        "salary": round(rng.uniform(25000, 180000), 2),
        "remote": rng.choice([True, False]),
        "performance": rng.choice(["Exceeds", "Meets", "Below"]),
    } for i in range(n)]
    return pd.DataFrame(rows)


def clinic_patients(n: int = 350, seed: int = 5) -> pd.DataFrame:
    rng = random.Random(seed)
    f = _fake(seed)
    rows = [{
        "patient_id": 70000 + i,
        "name": f.name(),
        "birth_date": f.date_of_birth(minimum_age=1, maximum_age=90).isoformat(),
        "blood_type": rng.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
        "weight_kg": round(rng.uniform(4, 120), 1),
        "last_visit": f.date_between("-1y", "today").isoformat(),
        "insured": rng.choice([True, False]),
    } for i in range(n)]
    return pd.DataFrame(rows)


def inventory(n: int = 450, seed: int = 6) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = [{
        "sku": f"SKU-{i:05d}",
        "product_name": f"Item {rng.randint(1, 200)} v{rng.randint(1, 5)}",
        "warehouse": rng.choice(["MNL-1", "MNL-2", "CEB-1", "DVO-1"]),
        "stock": rng.randint(0, 5000),
        "unit_cost": round(rng.uniform(1, 500), 2),
        "restock_date": pd.Timestamp("2025-01-01")
        + pd.Timedelta(days=rng.randint(0, 500)),
        "discontinued": rng.choice([True, False]),
    } for i in range(n)]
    df = pd.DataFrame(rows)
    df["restock_date"] = df["restock_date"].dt.strftime("%Y-%m-%d")
    return df


DATASETS = {
    "titanic_style": titanic_style,
    "retail_orders": retail_orders,
    "ph_customers": ph_customers,
    "employees": employees,
    "clinic_patients": clinic_patients,
    "inventory": inventory,
}
