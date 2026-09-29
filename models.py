from dataclasses import dataclass
from typing import Optional


@dataclass
class ImportBatch:
    id: Optional[int]
    file_name: str
    imported_at: str
    label: str


@dataclass
class BpasItem:
    id: Optional[int]
    batch_id: int
    category_uacs_school: str
    pap_name: str
    general_description: str
    item_description: str
    gad_category: str
    accounting_title: str
    mode_of_procurement: str
    app_for: str
    app_cs: str
    unit_price: float
    qty: float
    unit: str
    total_amount: float
