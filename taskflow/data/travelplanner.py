"""Loaders for the public TravelPlanner release (osunlp/TravelPlanner on Hugging Face).

Each query row ships its own slice of the TravelPlanner database as
``reference_information``: a list of {Description, Content} records whose
Content is a pandas ``to_string()`` table. We parse those tables into plain
records so the rest of the system never touches raw strings.

Only 3-day, single-destination queries are used in v0.
"""

from __future__ import annotations

import ast
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

csv.field_size_limit(10**9)

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
HF_BASE = "https://huggingface.co/datasets/osunlp/TravelPlanner/resolve/main"
SPLIT_FILES = ("train.csv", "validation.csv", "test.csv")

ATTR_COLS = ["Name", "Latitude", "Longitude", "Address", "Phone", "Website", "City"]
REST_COLS = ["Name", "Average Cost", "Cuisines", "Aggregate Rating", "City"]
ACC_COLS = ["NAME", "price", "room type", "house_rules", "minimum nights",
            "maximum occupancy", "review rate number", "city"]
FLIGHT_COLS = ["Flight Number", "Price", "DepTime", "ArrTime", "ActualElapsedTime",
               "FlightDate", "OriginCityName", "DestCityName", "Distance"]


@dataclass
class Flight:
    number: str
    price: float
    dep: str
    arr: str
    date: str
    origin: str
    dest: str


@dataclass
class Ground:
    mode: str  # "self-driving" | "taxi"
    origin: str
    dest: str
    cost: float
    duration: str


@dataclass
class Restaurant:
    name: str
    cost: float
    cuisines: list[str]
    rating: float
    city: str


@dataclass
class Accommodation:
    name: str
    price: float
    room_type: str
    house_rules: str
    min_nights: float
    max_occupancy: int
    rating: float
    city: str


@dataclass
class Attraction:
    name: str
    city: str


@dataclass
class CityDB:
    """Everything the planner may use for one trip."""

    attractions: list[Attraction] = field(default_factory=list)
    restaurants: list[Restaurant] = field(default_factory=list)
    accommodations: list[Accommodation] = field(default_factory=list)
    flights: dict[tuple[str, str, str], list[Flight]] = field(default_factory=dict)
    ground: dict[tuple[str, str, str], Ground] = field(default_factory=dict)


@dataclass
class Query:
    qid: str
    source_split: str
    org: str
    dest: str
    dates: list[str]
    people: int | None
    budget: float | None
    local_constraint: dict
    text: str
    level: str
    db: CityDB
    annotated_plan: list[dict] | None = None


def _split_table(content: str, cols: list[str]) -> list[list[str]]:
    lines = [ln for ln in content.split("\n") if ln.strip()]
    if not lines:
        return []
    header = lines[0]
    ends, start = [], 0
    for c in cols:
        pos = header.find(c, start)
        if pos < 0:
            raise ValueError(f"column {c!r} not found in header {header!r}")
        ends.append(pos + len(c))
        start = pos + len(c)
    rows = []
    for ln in lines[1:]:
        cells, prev = [], 0
        for i, e in enumerate(ends):
            cell = ln[prev:] if i == len(ends) - 1 else ln[prev:e]
            cells.append(cell.strip())
            prev = e
        rows.append(cells)
    return rows


def _num(s: str, default: float = 0.0) -> float:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return default


def parse_reference_information(ref: list[dict]) -> CityDB:
    db = CityDB()
    for rec in ref:
        desc, content = rec["Description"], rec["Content"]
        if not isinstance(content, str) or content.startswith("There is no"):
            continue
        if desc.startswith("Attractions in"):
            for r in _split_table(content, ATTR_COLS):
                db.attractions.append(Attraction(name=r[0], city=r[6]))
        elif desc.startswith("Restaurants in"):
            for r in _split_table(content, REST_COLS):
                name = re.sub(r"^\s*\d+\s+", "", r[0])
                db.restaurants.append(Restaurant(
                    name=name, cost=_num(r[1]),
                    cuisines=[c.strip() for c in r[2].split(",") if c.strip()],
                    rating=_num(r[3]), city=r[4]))
        elif desc.startswith("Accommodations in"):
            for r in _split_table(content, ACC_COLS):
                db.accommodations.append(Accommodation(
                    name=r[0], price=_num(r[1]), room_type=r[2],
                    house_rules="" if r[3] in ("NaN", "nan") else r[3],
                    min_nights=_num(r[4], 1.0), max_occupancy=int(_num(r[5], 1.0)),
                    rating=_num(r[6]), city=r[7]))
        elif desc.startswith("Flight from"):
            m = re.match(r"Flight from (.+) to (.+) on (\d{4}-\d{2}-\d{2})", desc)
            if not m:
                continue
            key = (m.group(1), m.group(2), m.group(3))
            db.flights[key] = [
                Flight(number=r[0], price=_num(r[1]), dep=r[2], arr=r[3], date=r[5],
                       origin=r[6], dest=r[7])
                for r in _split_table(content, FLIGHT_COLS)
            ]
        elif desc.startswith(("Self-driving from", "Taxi from")):
            m = re.match(r"(self-driving|taxi), from (.+) to (.+), duration: (.+?), "
                         r"distance: .+?, cost: ([\d,.]+)", content.strip())
            if not m:
                continue
            g = Ground(mode=m.group(1), origin=m.group(2), dest=m.group(3),
                       duration=m.group(4), cost=_num(m.group(5)))
            db.ground[(g.mode, g.origin, g.dest)] = g
    return db


def ensure_downloaded(raw_dir: Path = RAW_DIR) -> None:
    import urllib.request

    raw_dir.mkdir(parents=True, exist_ok=True)
    for f in SPLIT_FILES:
        p = raw_dir / f
        if not p.exists():
            urllib.request.urlretrieve(f"{HF_BASE}/{f}", p)


def load_queries(raw_dir: Path = RAW_DIR) -> list[Query]:
    """All 3-day single-city queries from the three public files (downloaded on first use)."""
    ensure_downloaded(raw_dir)
    out: list[Query] = []
    for f in SPLIT_FILES:
        split = f.split(".")[0]
        with open(raw_dir / f) as fh:
            for i, row in enumerate(csv.DictReader(fh)):
                if row["days"] != "3" or row.get("visiting_city_number", "1") != "1":
                    continue
                ref = ast.literal_eval(row["reference_information"])
                db = parse_reference_information(ref)
                plan = None
                if row.get("annotated_plan"):
                    plan = ast.literal_eval(row["annotated_plan"])[1]
                out.append(Query(
                    qid=f"{split}-{i:04d}", source_split=split,
                    org=row["org"], dest=row["dest"], dates=ast.literal_eval(row["date"]),
                    people=int(row["people_number"]) if row.get("people_number") else None,
                    budget=float(row["budget"]) if row.get("budget") else None,
                    local_constraint=ast.literal_eval(row["local_constraint"])
                    if row.get("local_constraint") else {},
                    text=row["query"], level=row["level"], db=db, annotated_plan=plan))
    return out
