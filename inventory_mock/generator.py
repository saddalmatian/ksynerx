from faker import Faker

fake = Faker("vi_VN")


def build_initial_products(count: int = 20) -> dict[str, dict]:
    products: dict[str, dict] = {}
    for i in range(1, count + 1):
        partner_sku = f"P{i:03d}"
        product = {
            "productId": i,
            "partnerSKU": partner_sku,
            "sku": f"SKU-{i:03d}",
            "productName": fake.catch_phrase().title(),
            "color": fake.color_name(),
            "size": fake.random_element(elements=["S", "M", "L", "XL", "Full"]),
            "description": fake.sentence(nb_words=8),
            "assetType": "Single",
            "isActive": True,
            "hasSerial": fake.boolean(),
            "hasExpiration": fake.boolean(),
            "outboundType": "NotDefined",
            "hsCode": str(fake.random_number(digits=6, fix_len=True)),
            "countryOfOrigin": "VN",
            "price": fake.random_number(digits=6, fix_len=True),
            "stock": fake.random_int(min=0, max=200),
            "units": [{"unitCode": "CAI", "unitName": "Cái", "isBaseUnit": True}],
            "categories": [{"categoryCode": "GEN", "categoryName": "General"}],
        }
        products[partner_sku] = product
    return products
