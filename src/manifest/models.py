"""
Data models for Amazon liquidation manifest rows.

A manifest is a CSV file provided by Amazon (or liquidation platforms like B-Stock)
that describes the contents of a pallet or truckload of returned/overstock items.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ManifestRow:
    """Represents a single item row from a liquidation manifest CSV."""
    lpn: str = ""
    asin: str = ""
    item_desc: str = ""
    department: str = ""
    category: str = ""
    subcategory: str = ""
    condition: str = ""
    qty: int = 1
    total_retail: Optional[float] = None
    unit_retail: Optional[float] = None
    cost: Optional[float] = None
    total_cost: Optional[float] = None
    itempkgweight: Optional[float] = None
    itempkgweightuom: str = ""
    currency_code: str = ""
    pallet_id: str = ""
    pkgid: str = ""
    fc: str = ""
    gl: str = ""
    gl_description: str = ""
    categorycode: str = ""
    subcatcode: str = ""
    upc: str = ""
    ean: str = ""
    fcsku: str = ""
    fnsku: str = ""
    bol: str = ""
    carrier: str = ""
    shiptocity: str = ""
    listing_id: str = ""
    slot_size: str = ""
    is_parcel: Optional[bool] = None
    date_in: Optional[date] = None
    batch_id: Optional[str] = None

    def has_asin(self) -> bool:
        return bool(self.asin and self.asin.strip())

    def retail_value(self) -> float:
        """Best available retail value for this item."""
        if self.total_retail is not None:
            return self.total_retail
        if self.unit_retail is not None:
            return self.unit_retail * self.qty
        return 0.0
