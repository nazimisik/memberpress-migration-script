#!/usr/bin/env python3
import argparse, csv, os, json, re
from collections import OrderedDict
from typing import List, Dict, Tuple, Set, Optional

try:
    import yaml
except Exception:
    yaml = None


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    if path.lower().endswith((".yml", ".yaml")):
        if yaml is None:
            raise SystemExit("Config is YAML but PyYAML is not installed. pip install pyyaml")
        return yaml.safe_load(txt) or {}
    return json.loads(txt)


def read_csv_keep_order(path: str) -> Tuple[List[str], List[OrderedDict]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        headers = rdr.fieldnames or []
        rows: List[OrderedDict] = []
        for r in rdr:
            rows.append(OrderedDict((h, (r.get(h, "") if r.get(h, "") is not None else "")) for h in headers))
        return headers, rows


def write_csv_exact_headers(path: str, headers: List[str], rows: List[OrderedDict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({h: ("" if r.get(h) is None else r.get(h)) for h in headers})


def build_mapping(d: Optional[dict]) -> Dict[str, str]:
    """For IDs, use exact/trim-only matching—no lowercasing (IDs can be case-sensitive)."""
    if not d:
        return {}
    m: Dict[str, str] = {}
    for k, v in d.items():
        if k is None:
            continue
        m[str(k).strip()] = "" if v is None else str(v).strip()
    return m


def map_value_exact(val: str, mapping: Dict[str, str]) -> Tuple[str, bool]:
    """Map by exact or trimmed key only; return (new_value, did_map)."""
    if val is None:
        return "", False
    raw = str(val)
    if raw in mapping:
        return mapping[raw], True
    trimmed = raw.strip()
    if trimmed in mapping:
        return mapping[trimmed], True
    return raw, False


def map_multivalue_cell_preserve_separators(cell: str, mapping: Dict[str, str]) -> Tuple[str, bool]:
    """
    Map tokens inside a multi-value cell while preserving original separators/spaces.
    Splits on , ; | with surrounding spaces kept as separate parts.
    """
    if not cell:
        return cell, False
    parts = re.split(r'(\s*[;,|]\s*)', cell)
    changed = False
    for i in range(0, len(parts), 2):
        token = parts[i]
        if token.strip() == "":
            continue
        new, did = map_value_exact(token, mapping)
        if did:
            parts[i] = new
            changed = True
    return "".join(parts), changed


def apply_column_value_mapping(
    rows: List[OrderedDict],
    columns: List[str],
    mapping: Dict[str, str],
    forbid_columns: Set[str] = frozenset()
) -> Tuple[int, Set[str]]:
    """
    Map values only in the specified columns (headers unchanged).
    Returns (rows_changed_count, unmapped_samples_set)
    """
    if not rows or not columns or not mapping:
        return 0, set()

    changed_rows = 0
    unmapped_samples: Set[str] = set()

    present_cols = [c for c in columns if rows and c in rows[0]]
    target_cols = [c for c in present_cols if c not in forbid_columns]

    for r in rows:
        row_changed = False
        for col in target_cols:
            val = r.get(col, "")
            if val != "":
                new, did = map_value_exact(val, mapping)
                if did:
                    r[col] = new
                    row_changed = True
                else:
                    if len(unmapped_samples) < 20:
                        unmapped_samples.add(str(val))
        if row_changed:
            changed_rows += 1

    return changed_rows, unmapped_samples


def apply_multivalue_mapping(
    rows: List[OrderedDict],
    columns: List[str],
    mapping: Dict[str, str]
) -> Tuple[int, Set[str]]:
    """Map values inside multi-value cells; returns (rows_changed_count, unmapped_token_samples)."""
    if not rows or not columns or not mapping:
        return 0, set()

    changed_rows = 0
    unmapped_samples: Set[str] = set()

    present_cols = [c for c in columns if rows and c in rows[0]]

    for r in rows:
        row_changed = False
        for col in present_cols:
            val = r.get(col, "")
            if val == "":
                continue
            new_cell, did_any = map_multivalue_cell_preserve_separators(val, mapping)
            if did_any:
                r[col] = new_cell
                row_changed = True
            else:
                tokens = [t for t in re.split(r'[;,|]', val) if t.strip()]
                for tok in tokens:
                    if tok.strip() not in mapping and len(unmapped_samples) < 20:
                        unmapped_samples.add(tok.strip())
                        break
        if row_changed:
            changed_rows += 1

    return changed_rows, unmapped_samples


def build_id_map_sequential(rows: List[OrderedDict], id_col: str, start_at: int) -> Dict[str, str]:
    """
    Build a mapping old_id -> new_id using a simple sequence:
    First occurrence gets start_at, next gets start_at+1, etc. (order of rows).
    All references to the same old_id will map to the same new_id.
    """
    mapping: Dict[str, str] = {}
    current = start_at
    for r in rows:
        old = str(r.get(id_col, "")).strip()
        if old not in mapping:
            mapping[old] = str(current)
            current += 1
    return mapping


def remap_column_using_map(rows: List[OrderedDict], col: str, id_map: Dict[str, str]):
    """In place: r[col] = id_map[old] if present (exact/trimmed); leaves value as-is if not found."""
    for r in rows:
        old = str(r.get(col, "")).strip()
        if old in id_map:
            r[col] = id_map[old]


def main():
    ap = argparse.ArgumentParser(
        description=(
            "MemberPress migration: preserve headers; map product/gateway values across ALL files; "
            "map members.memberships; assign NEW sequential IDs starting from config; "
            "update FKs (user_id, sub_id) to new IDs; keep subscr_id untouched."
        )
    )
    ap.add_argument("--members", required=True, help="Members export CSV (source)")
    ap.add_argument("--subscriptions", required=True, help="Subscriptions export CSV (source)")
    ap.add_argument("--transactions", required=True, help="Transactions export CSV (source)")
    ap.add_argument("--config", required=True, help="Config YAML/JSON with mappings and start_ids")
    ap.add_argument("--outdir", required=True, help="Output directory")
    args = ap.parse_args()

    cfg = load_config(args.config)

    default_product_cols = {
        "members": ["memberships", "inactive_memberships"],
        "subscriptions": ["product_id", "membership_id", "product_name", "membership", "product"],
        "transactions":  ["product_id", "membership_id", "product_name", "membership", "product"],
    }
    default_gateway_cols = {
        "subscriptions": ["gateway_id", "gateway"],
        "transactions":  ["gateway_id", "gateway"],
    }

    product_cols_cfg = cfg.get("product_columns") or {}
    gateway_cols_cfg = cfg.get("gateway_columns") or {}

    product_cols = {
        "members": product_cols_cfg.get("members", default_product_cols["members"]),
        "subscriptions": product_cols_cfg.get("subscriptions", default_product_cols["subscriptions"]),
        "transactions": product_cols_cfg.get("transactions", default_product_cols["transactions"]),
    }
    gateway_cols = {
        "subscriptions": gateway_cols_cfg.get("subscriptions", default_gateway_cols["subscriptions"]),
        "transactions":  gateway_cols_cfg.get("transactions",  default_gateway_cols["transactions"]),
    }

    hard_forbid_value_columns: Set[str] = {"subscr_id"}

    products_map = build_mapping((cfg.get("mappings") or {}).get("products"))
    gateways_map = build_mapping((cfg.get("mappings") or {}).get("gateways"))

    start_cfg = (cfg.get("start_ids") or {})
    try:
        start_members = int(start_cfg.get("members"))
        start_subs = int(start_cfg.get("subscriptions"))
        start_txs = int(start_cfg.get("transactions"))
    except Exception:
        raise SystemExit("start_ids.members / start_ids.subscriptions / start_ids.transactions must be provided as integers.")

    mem_headers, mem_rows = read_csv_keep_order(args.members)
    sub_headers, sub_rows = read_csv_keep_order(args.subscriptions)
    tx_headers,  tx_rows  = read_csv_keep_order(args.transactions)

    if not (mem_rows or sub_rows or tx_rows):
        raise SystemExit("No rows found in inputs. Check your CSV paths/exports.")

    member_id_col = "ID" if "ID" in mem_headers else ("id" if "id" in mem_headers else None)
    if member_id_col is None:
        raise SystemExit("Members CSV must have an 'ID' (or 'id') column.")
    if "id" not in sub_headers:
        raise SystemExit("Subscriptions CSV must have an 'id' column.")
    if "id" not in tx_headers:
        raise SystemExit("Transactions CSV must have an 'id' column.")

    member_id_map = build_id_map_sequential(mem_rows, member_id_col, start_members)
    subs_id_map   = build_id_map_sequential(sub_rows, "id", start_subs)
    tx_id_map     = build_id_map_sequential(tx_rows,  "id", start_txs)

    remap_column_using_map(mem_rows, member_id_col, member_id_map)
    remap_column_using_map(sub_rows, "id",           subs_id_map)
    remap_column_using_map(tx_rows,  "id",           tx_id_map)

    if "user_id" in sub_headers:
        remap_column_using_map(sub_rows, "user_id", member_id_map)
    if "user_id" in tx_headers:
        remap_column_using_map(tx_rows, "user_id", member_id_map)
    if "sub_id" in tx_headers:
        remap_column_using_map(tx_rows, "sub_id",  subs_id_map)

    apply_multivalue_mapping(mem_rows, product_cols["members"], products_map)

    apply_column_value_mapping(sub_rows, product_cols["subscriptions"], products_map, forbid_columns=hard_forbid_value_columns)
    apply_column_value_mapping(sub_rows, gateway_cols["subscriptions"], gateways_map, forbid_columns=hard_forbid_value_columns)

    apply_column_value_mapping(tx_rows, product_cols["transactions"], products_map, forbid_columns=hard_forbid_value_columns)
    apply_column_value_mapping(tx_rows, gateway_cols["transactions"], gateways_map, forbid_columns=hard_forbid_value_columns)

    os.makedirs(args.outdir, exist_ok=True)
    members_out = os.path.join(args.outdir, "members_import.csv")
    subs_out    = os.path.join(args.outdir, "subscriptions_import.csv")
    tx_out      = os.path.join(args.outdir, "transactions_import.csv")

    write_csv_exact_headers(members_out, mem_headers, mem_rows)
    write_csv_exact_headers(subs_out,    sub_headers, sub_rows)
    write_csv_exact_headers(tx_out,      tx_headers,  tx_rows)

    print(f"Members:       {len(mem_rows)} -> {members_out} (ID starts @ {start_members})")
    print(f"Subscriptions: {len(sub_rows)} -> {subs_out} (id starts @ {start_subs})")
    print(f"Transactions:  {len(tx_rows)} -> {tx_out} (id starts @ {start_txs})")
    print("Done.")


if __name__ == "__main__":
    main()
