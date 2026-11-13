# Native product JSON field map

Observed November 12, 2026. These are observed fields, not a vendor-supported schema. All raw fields remain available under `product.raw`. No extra HTTP requests are required to obtain these fields.

Source: cookie-free `POST /assets/ajax/getProductAttributes.aspx?storeid=195`, form `type=product&product_id=660548`, XMLHttpRequest header. Response HTTP200, application/json; 4,117 bytes, no cf-mitigated header. Product660548 / SKU518159 was10.99 with original19.99 and stockTrue; store185 returned stockFalse.

| Field | Observed type | Meaning / limits |
|---|---|---|
| `action` | `str` | Request/analytics metadata; empty in product lookup. |
| `page_type` | `str` | Request/analytics metadata; empty in product lookup. |
| `action_type` | `str` | Request/analytics metadata; empty in product lookup. |
| `list_id` | `str` | Request/analytics metadata; empty in product lookup. |
| `recommendation_id` | `str` | Request/analytics metadata; empty in product lookup. |
| `item_id` | `str` | Item identifier; matched product ID in observed samples. |
| `product_id` | `str` | Canonical product ID; validate against the requested ID. |
| `short_sku` | `str` | Store SKU; differs from product ID. |
| `title` | `str` | Vendor product metadata; preserve verbatim. |
| `brand` | `str` | Vendor product metadata; preserve verbatim. |
| `brand_id` | `str` | Brand identifier. |
| `price` | `str` | Current item price in requested store context; decimal string, not cents. |
| `original_price` | `str` | Original price; do not assume it is a historical market price. |
| `discount` | `str` | Reported absolute dollar discount; preserve raw value. |
| `in_stock` | `str` | Store-sensitive boolean encoded as True/False strings; not a quantity. |
| `is_on_web` | `str` | Web listing flag. |
| `category_1` | `str` | Category label and ID separated by \|. |
| `coordinate_group` | `str` | Undocumented merchandising coordinate; not a verified aisle/bin location. |
| `map` | `str` | Undocumented field; not a verified minimum-advertised-price amount. |
| `average_rating` | `str` | Average customer rating as decimal string; aggregate only. |
| `number_reviews` | `str` | Review count as string; not review bodies. |
| `can_list` | `str` | Listing eligibility flag. |
| `can_pickup` | `str` | Pickup eligibility, independent of current store stock. |
| `can_ship` | `str` | Shipping eligibility; not a delivery commitment. |
| `deck` | `str` | Undocumented merchandising value. |
| `manufacturer_number` | `str` | Manufacturer part/model identifier. |
| `valuable_links` | `str` | Vendor merchandising label. |
| `shipping_days` | `str` | Reported shipping field; undocumented semantics, not a guaranteed delivery date. |
| `upc` | `str` | UPC identifier; preserve as string. |
| `has_proritycare_price` | `str` | Vendor spelling retained; care-price presence flag, not quoted price. |
| `showed_proritycare_price` | `str` | Vendor spelling retained; care-price display flag. |
| `has_member_price` | `str` | Member-price presence flag, not a member-price amount. |
| `showed_member_price` | `str` | Member-price display flag, not authentication or eligibility proof. |
| `z_features` | `str` | Flattened duplicate specification string; prefer structured rows. |
| `z_features_array` | `dict` | Structured specification rows under Root: Group, Feature, Value. |
| `key_feature_1` | `str` | Product highlight string; order retained. |
| `key_feature_2` | `str` | Product highlight string; order retained. |
| `key_feature_3` | `str` | Product highlight string; order retained. |
| `key_feature_4` | `str` | Product highlight string; order retained. |
| `key_feature_5` | `str` | Product highlight string; order retained. |
| `category_level_1` | `str` | Hierarchy label, short category ID and provider category ID separated by \|; may be empty. |
| `category_level_2` | `str` | Hierarchy label, short category ID and provider category ID separated by \|; may be empty. |
| `category_level_3` | `str` | Hierarchy label, short category ID and provider category ID separated by \|; may be empty. |
| `category_level_4` | `str` | Hierarchy label, short category ID and provider category ID separated by \|; may be empty. |
| `category_ids` | `str` | Provider category IDs separated by \|; distinguish from short category ID754. |
| `category_path` | `str` | Category hierarchy labels separated by \|. |
| `core` | `str` | Undocumented field. |
| `ip_buyer_code` | `str` | Undocumented buyer metadata; preserve without assigning business semantics. |
| `x_color` | `str` | Color terms; can describe shade more precisely than the specifications Color row. |
| `type` | `str` | Requested handler operation: product. |

## Specifications without page scraping

`z_features_array.Root` contains rows with `Group`, `Feature`, `Value`. For the matte Denim sample this includes materialPLA, colorBlue, diameter1.75mm, print temperature190–200°C, plate temperature25–60°C, speed30–70mm/s, spool weight1kg, package contents and warranty. Preserve vendor units and values: these are manufacturer/store claims, not independently measured print profiles.

## What the endpoint does not establish

- Exact stock quantity or stock cap. `in_stock` is boolean.
- Additional bulk or mix-and-match pricing tiers. Discount and member flags are not a quantity quote.
- Open-box unit identifiers, conditions and prices.
- Review bodies, photos or answered customer questions.
- Guaranteed arrival dates or physical shelf/bin location.

## Reproduce

```sh
curl 'https://www.microcenter.com/assets/ajax/getProductAttributes.aspx?storeid=195' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data 'type=product&product_id=660548'
```

Use the CLI for paced/cached requests. The curl example is a single read-only lookup.
