"""Generate messy test files for manually exercising YODA.

Run:  python test_data/make_test_data.py
Creates test_data/{employees_messy.csv, orders_messy.xlsx, shop.sqlite}
Every kind of dirt YODA handles is planted somewhere in these files.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
random.seed(7)

first = ["Ana", "Ben", "Carla", "Diego", "Eva", "Fe", "Gio", "Hana", "Ivan",
         "Jade", "Ken", "Lia", "Mia", "Noel", "Omar", "Pia", "Rey", "Sol"]
last = ["Cruz", "Reyes", "Lim", "Tan", "Santos", "Uy", "Sy", "Ong", "Go",
        "Chua", "Lao", "Del Rosario", "Torres", "Bautista"]


def employees(n=60) -> pd.DataFrame:
    date_styles = ["2023-{m:02d}-{d:02d}", "{m:02d}/{d:02d}/2023",
                   "March {d}, 2023", "2023{m:02d}{d:02d}"]
    phone_styles = ["09{d9}", "+639{d9}", "0917 {a} {b}", "63-917-{a}-{b}"]
    rows = []
    for i in range(n):
        name = f"{random.choice(first)} {random.choice(last)}"
        if i % 6 == 0:
            name = " " + name          # leading space
        if i % 9 == 0:
            name = name.replace(" ", "  ")  # double space
        m, d = random.randint(1, 12), random.randint(1, 28)
        d9 = "".join(random.choices("0123456789", k=9))
        a, b = d9[:3], d9[3:7]
        rows.append({
            "Full Name": name,
            "Department": random.choice(["Sales", "sales", "SALES", "HR", "hr",
                                          "IT", "it", "Finance"]),
            "Hire Date": random.choice(date_styles).format(m=m, d=d, d9=d9),
            "Mobile": random.choice(phone_styles).format(d9=d9, a=a, b=b),
            "Salary": random.choice(["₱{:,}.00", "PHP {}", "{}"]).format(
                random.randint(18, 90) * 1000),
            "Years": str(random.randint(0, 30)),
            "Remote": random.choice(["yes", "no", "TRUE", "False", "y", "n"]),
            "Status": random.choice(["Active", "active", "ACTIVE", "Inactive",
                                     "inactive"]),
            "Legacy ID": "",           # entirely blank column
        })
    df = pd.DataFrame(rows)
    # nulls, outliers, dupes, blank rows
    df.loc[df.sample(6, random_state=1).index, "Years"] = None
    df.loc[df.sample(5, random_state=2).index, "Mobile"] = None
    df.loc[3, "Salary"] = "₱9,999,999.00"          # outlier
    df.loc[17, "Years"] = "250"                     # impossible value
    df = pd.concat([df, df.iloc[[2, 11, 25]]], ignore_index=True)  # dupes
    for _ in range(3):                              # blank rows
        df.loc[len(df)] = {c: None for c in df.columns}
    return df.sample(frac=1, random_state=3).reset_index(drop=True)


def orders(n=80) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "OrderID": f"ORD-{1000 + i}",
            "customer": f"{random.choice(first)} {random.choice(last)}",
            "order date": random.choice(
                ["2024-{m:02d}-{d:02d}", "{m:02d}/{d:02d}/2024"]).format(
                m=random.randint(1, 12), d=random.randint(1, 28)),
            "Total": random.choice(["₱{:,}.50", "PHP {}", "$ {}"]).format(
                random.randint(1, 90) * 100),
            "Qty": str(random.randint(1, 12)),
            "Channel": random.choice(["Online", "online", "ONLINE", "Store",
                                      "store", "Phone"]),
            "Notes": random.choice(["", "  ", "rush", "gift wrap", ""]),
        })
    df = pd.DataFrame(rows)
    df.loc[df.sample(7, random_state=4).index, "Qty"] = None
    df.loc[5, "Total"] = "₱999,999.50"
    df = pd.concat([df, df.iloc[[1, 9]]], ignore_index=True)
    return df


emp = employees()
emp.to_csv(HERE / "employees_messy.csv", index=False)
orders().to_excel(HERE / "orders_messy.xlsx", index=False)

db = HERE / "shop.sqlite"
db.unlink(missing_ok=True)
with sqlite3.connect(db) as con:
    employees(40).to_sql("staff", con, index=False)
    orders(50).to_sql("orders", con, index=False)

print("wrote:")
for f in ("employees_messy.csv", "orders_messy.xlsx", "shop.sqlite"):
    print("  test_data/" + f)
