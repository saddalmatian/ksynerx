"""Generate sample/products.xlsx for the Excel upload demo."""

from __future__ import annotations

from pathlib import Path

from faker import Faker
from openpyxl import Workbook

HEADERS = [
    "partnerSKU",
    "sku",
    "productName",
    "color",
    "size",
    "description",
    "assetType",
    "isActive",
    "price",
    "stock",
]

OUT_PATH = Path(__file__).resolve().parents[1] / "sample" / "products.xlsx"


def main() -> None:
    fake = Faker("vi_VN")
    Faker.seed(42)
    wb = Workbook()
    ws = wb.active
    ws.title = "products"
    ws.append(HEADERS)

    colors = ["Black", "White", "Blue", "Red", "Silver"]
    sizes = ["S", "M", "L", "XL", "Full"]
    for i in range(1, 21):
        ws.append(
            [
                f"XLP{i:03d}",
                f"SKU-XL-{i:03d}",
                fake.catch_phrase().title()[:60],
                colors[i % len(colors)],
                sizes[i % len(sizes)],
                fake.sentence(nb_words=8),
                "SIMPLE",
                i % 7 != 0,
                fake.random_number(digits=6, fix_len=True),
                fake.random_int(min=0, max=500),
            ]
        )

    # Row 22: duplicate of row 1 (dedup demo on re-upload)
    ws.append([c.value for c in ws[2]])

    # Row 23: intentionally invalid (missing partnerSKU and sku)
    ws.append(
        [
            None,
            None,
            "Broken row",
            "Green",
            "M",
            "no ids",
            "SIMPLE",
            True,
            1000,
            5,
        ]
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_PATH)
    print(f"wrote {OUT_PATH} (23 data rows: 20 unique + 1 duplicate + 1 invalid)")


if __name__ == "__main__":
    main()
