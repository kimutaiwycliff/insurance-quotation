# catalog

Items a tenant sells: name, unit, default price, currency and a jurisdiction-pack tax code
(`GET/POST/PATCH /items`). Invoice lines may reference an item (price and tax code copied, editable).
Items are hidden (`active: false`), never deleted. Managing items needs `catalog:manage`.
