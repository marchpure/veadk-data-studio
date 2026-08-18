from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import os
import re
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


SCHEMA_VERSION = "oracle.sales.snapshot.manifest.v2"
SOURCE_SCHEMA = "dnyxlstest"
DATA_THROUGH = "2026-08-15"
ORIGINAL_PREFIX = "oracle-local-extract/20260817-114544-arkclaw"
SANITIZED_PREFIX_TEMPLATE = "oracle-local-extract-sanitized/{stamp}-arkclaw"

DIRECT_IDENTIFIER_COLUMNS = {
    "CUST_ID",
    "CUST_NAME",
    "CUST_ADDR",
    "CUST_TEL",
    "VIPID",
    "VIPCXID",
    "MARKETVIPCARDNO",
    "BOARDINGPASS",
    "PASSPORT",
}
CONTACT_COLUMNS = {
    "ADDRESS",
    "PHONE",
    "MOBILEPHONE",
    "LINKMAN",
    "CONSIGNEE",
    "ZIPCODE",
}
FREE_TEXT_COLUMNS = {
    "REMARK",
    "MEMO",
    "FJ",
    "PIC",
    "THIRDPIC",
    "THIRDPICRANK",
    "ALLPROMOTIONSCRIPT",
    "CHANGEPRICENOTE",
    "BEWRITE",
}
STAFF_NAME_COLUMNS = {"STAFFNAME"}
STAFF_IDENTIFIER_COLUMNS = {"STAFFID", "CASHIER_ID", "INACCOUNT_STAFF", "UPSTAFF", "CREATESTAFF", "CLOCKPERSONNEL"}
SENSITIVE_COLUMNS = (
    DIRECT_IDENTIFIER_COLUMNS | CONTACT_COLUMNS | FREE_TEXT_COLUMNS | STAFF_NAME_COLUMNS | STAFF_IDENTIFIER_COLUMNS
)

EXPECTED_ROW_COUNTS = {
    "P_BL_SELL_HD": 4279,
    "P_BL_SELL_DT": 7006,
    "P_ARC_STORE": 433,
    "D_ARC_ITEM": 818856,
    "D_ARC_CLASS": 300,
    "D_ARC_BRAND": 17,
    "V_STORE_STAFF": 352,
    "P_ARC_BRAND": 447,
}

ALLOWLIST: dict[str, list[str]] = {
    "P_BL_SELL_HD": [
        "SERIES",
        "BILLID",
        "STOREID",
        "POSID",
        "OPERATETIME",
        "ACCOUNT_SALES",
        "CUST_TYPE",
        "SELLDATE",
        "SELLTIME",
        "DEDUCTIBLE_AMOUNT",
        "ACCOUNT_PAID",
        "ODD_CHANGE",
        "hmac_sha256(STAFFID) AS STAFF_KEY",
        "SELLSTATEID",
        "SELLTYPECODE",
        "OLDBILLIDID",
        "ACCOUNT_PAYABLE",
        "SELLDAILYID",
        "CANCELSIGN",
        "POSINPUTSIGN",
        "MAKE_POINT_SIGN",
        "CUST_POINT",
        "WIPE_ZERO",
        "SALESMODE",
        "ORDERFORMID",
        "MAKEDKCOSTSIGN",
        "POST_DATE",
        "POST_FLAG",
        "IMPORT_DATE",
        "IMPORT_FLAG",
        "INACCOUNT_DATE",
        "STORAGEID",
        "FACT_PICK_GOOD_DATE",
        "PICK_FLAG",
        "RETURN_GOODS_ATTR",
        "UPTIME",
        "QTY",
        "BANKPAYID",
        "STATUS",
        "VIPJF",
        "INVSTATUS",
        "INVBILLID",
        "SCHDBILLID",
        "UPTIMESTAMP",
        "DISCOUNTAMOUNT",
        "ZKBILLID",
        "ZKTYPE",
        "ACCOUNTCOMPANYID",
        "SYNSIGN",
        "SYNTIME",
        "IMPORTSIGN",
        "DSTSYNSIGN",
        "DSTSYNTIME",
        "BISYNSIGN",
        "PRESELLDATE",
        "WORKSTATUS",
        "SYSYNSIGN",
        "SYSYNTIME",
        "SALESTYPE",
        "VATRATE",
        "VAT",
        "NET",
        "BASEACCOUNT_SALES",
        "BASEACCOUNT_PAID",
        "BASEODD_CHANGE",
        "BASEACCOUNT_PAYABLE",
        "BASEWIPE_ZERO",
        "BASEVAT",
        "BASENET",
        "SHOWSIGN",
        "FREESHIPSIGN",
        "FRSTORE",
        "PARTRETURNLIMIT",
        "SELLERTAX",
    ],
    "P_BL_SELL_DT": [
        "SERIES",
        "ITEMID",
        "BILLID",
        "SELLDAILYID",
        "FORMERRETAILPRICE",
        "FACTRETAILPRICE",
        "QTY",
        "FACTRETAILMONEY",
        "SALESPROMOTIONID",
        "CHANGEBEFOREPRICE",
        "hmac_sha256(STAFFID) AS STAFF_KEY",
        "GROUPID",
        "POINT_SIGN",
        "GIFTSIGN",
        "PROMOTIONSIGN",
        "DISCOUNT",
        "RETURNQTY",
        "REALPRICE",
        "REALAMOUNT",
        "UNITS",
        "CANCELSIGN",
        "UPTIME",
        "SHARETYPE",
        "FACTDISCOUNT",
        "UPTIMESTAMP",
        "DIFFERENCEPRICE",
        "CHANGEAMOUNT",
        "CUST_POINT",
        "BISYNSIGN",
        "SALESTYPE",
        "UNIQUENO",
        "VATRATE",
        "VAT",
        "NET",
        "BASEFORMERRETAILPRICE",
        "BASEFACTRETAILPRICE",
        "BASEFACTRETAILMONEY",
        "BASEREALPRICE",
        "BASEREALAMOUNT",
        "BASEVAT",
        "BASENET",
        "BASEVATRATE",
        "SINGLETICKET",
        "SOURCESERIES",
    ],
    "P_ARC_STORE": [
        "SERIES",
        "STOREID",
        "STORENAME",
        "COMPANYID",
        "OPENDATE",
        "CLOSEDATE",
        "CLOSESIGN",
        "PRICEAREAID",
        "OLDSTOREID",
        "ERPSTOREID",
        "AREAID",
        "SMTYPE",
        "STORETYPE",
        "STOREPAYROLL",
        "POSID",
        "MANAGETYPE",
        "STORETYPE1",
        "OLDOAID",
        "OLDGPID",
        "CANCELSIGN",
        "UPTIME",
        "CHANGEPRICE",
        "POSVERSION",
        "CONTROLJXC",
        "STATUS",
        "STOREAREA",
        "GRADE",
        "UPSTOREID",
        "JYTYPE",
        "PRV_ID",
        "CITY_ID",
        "CITY_AREA_ID",
        "STOREAREA1",
        "BUID",
        "JYAREAID",
        "QJTYPE",
        "ONLINEDATE",
        "STAFFS",
        "CWCOMPANYID",
        "VSSIGN",
        "DVID",
        "O2OGRADE",
        "UPTIMESTAMP",
        "COSTSIGN",
        "ACCOUNTCOMPANYID",
        "BASICFACTMONEYTYPE",
        "ENSTORENAME",
        "ENSIMPLESTORENAME",
        "OB_UNIONKEY",
        "QDPP",
        "DPDW",
        "SCTX",
        "ZLLX",
        "DPWZ",
        "SYNSIGN",
        "SYNTIME",
        "BIID",
        "JMSIGN",
        "JYTYPE2",
        "SWH",
        "MDBZ",
        "BHBZ",
        "DYS",
        "SYMJ",
        "ZCRQ",
        "KYND",
        "SDHF",
        "SAPSTOREID",
        "SAPCOMPANYID",
        "PRCTR",
        "COSTCTR",
        "CREATETIME",
        "STOREJC",
        "POINT",
        "DSTAREA",
        "BEGINTIME",
        "ENDTIME",
        "CONTROLAREA1",
        "CONTROLAREA2",
        "TIMEZONE",
        "CMSID",
        "COUNTRY",
        "PLATFORM",
        "CATEGORY",
        "ONOFFLINE",
        "JHSX",
        "ISBRANDSTORE",
        "BRANDSTOREID",
        "AMSTOREID",
        "RFIDFLAG",
        "IFHANDLEDEV",
        "P65STOREID",
        "JMFXSTOREID",
    ],
    "D_ARC_ITEM": [
        "SERIES",
        "WEIGHT",
        "PACKMEASURE",
        "ITEMID",
        "ITEMTYPE",
        "ITEMDESIGN",
        "ITEMNAME",
        "BARCODE",
        "BCODEID",
        "MCODEID",
        "SCODEID",
        "BRANDID",
        "SEASONID",
        "SIZEID",
        "SELLSIGN",
        "ITEMCOST",
        "RETAILPRICE",
        "UNITS",
        "SIZEGROUPID",
        "INPUETIME",
        "SYEAR",
        "SEX",
        "COLORID",
        "COLORNAME",
        "FABRIC",
        "ITEMSERIES",
        "CATAGORY",
        "LISTDATE",
        "SIZENAME",
        "TAGPRICE",
        "CANCELSIGN",
        "UPTIME",
        "SHOP_ITEMID",
        "OLDITEMID",
        "RCODEID",
        "MAINCOLOR",
        "STATUS",
        "UPTIMESTAMP1",
        "LASTUPTIMESTAMP",
        "UPTIMESTAMP",
        "ACCOUNTCOMPANYID",
        "ENITEMNAME",
        "ENSIMPLEITEMNAME",
        "ITEMSERIES2",
        "MARKETING",
        "COMBINATION",
        "UPANDDOWN",
        "PRICEBAND",
        "LONGANDSHORTLOADING",
        "BIGSMALLKIDS",
        "TYPEVERSION",
        "POP",
        "LISTEDBATCH",
        "BMATERIAL",
        "SDATE",
        "NDATE",
        "MDATE",
        "PHJ",
        "OLD_MAT_NO",
        "ZZ01",
        "ZZ02",
        "ZZ21",
        "ZZ22",
        "KEYPOP",
        "KM",
        "SYNSIGN",
        "SYNTIME",
        "SAPSYNSIGN",
        "SAPSYNTIME",
        "SAPSYNSIGN1",
        "SAPSYNSIGN2",
        "IPCODE",
        "IPQTY",
        "CASEQTY",
        "NETWEIGHT",
        "GROSSWEIGHT",
        "EBSIGN",
        "COUNTRY",
        "CREATETIME",
        "ZZ04",
        "ENSEX",
        "TWITEMNAME",
        "TWSIMPLEITEMNAME",
        "THEME",
        "PROCURETYPE",
        "TECHNOLOGY",
        "ENCOLORNAME",
        "LAUNCHDATE",
        "DISCOUNTDATE",
        "AGEGROUP",
        "SMC",
        "REGION",
        "SFBCODEID",
        "POINTSIGN",
        "ZISRFID",
        "ZSALES_DL",
        "ZEAN69",
    ],
    "D_ARC_CLASS": [
        "SERIES",
        "CLASSID",
        "CLASSNAME",
        "UPCLASSID",
        "CANCELSIGN",
        "UPTIME",
        "UPTIMESTAMP",
        "TYPED",
        "SIMPLEID",
        "TAXCODE",
        "SHOWSIGN",
        "COUNTSIGN",
        "ACCOUNTCOMPANYID",
        "ZKBCSIGN",
        "ENCLASSNAME",
        "ENSIMPLECLASSNAME",
        "FILAID",
        "DESCENTEID",
        "SPANDIID",
        "REFUNDSIGN",
        "SHARESIGN",
        "ANTAPLUSID",
        "KINGKOWID",
        "CHECKNUMSIGN",
        "ANTAID",
        "MYID",
        "SELLSIGN",
        "TICKETSIGN",
        "CHANGESIGN",
    ],
    "D_ARC_BRAND": [
        "SERIES",
        "BRANDID",
        "BRANDNAME",
        "BRANDENAME",
        "BUID",
        "CANCELSIGN",
        "SIMPLENAME",
        "UPTIME",
        "UPTIMESTAMP",
        "STORAGEID",
        "MERGEBRANDID",
        "REMOVESIGN",
        "ACCOUNTCOMPANYID",
        "SAPID",
        "APIBRANDID",
        "APICODE",
        "ENBRANDNAME",
        "PREFIXSTR",
        "RETURNSTORAGEID",
        "UNLOCKSIGN",
        "SIZEGROUP",
    ],
    "V_STORE_STAFF": [
        "hmac_sha256(STAFFID) AS STAFF_KEY",
        "STOREID",
        "STORENAME",
        "AREAID",
        "AREANAME",
        "CANCELSIGN",
    ],
    "P_ARC_BRAND": [
        "SERIES",
        "STOREID",
        "BRANDID",
        "BRANDNAME",
        "CANCELSIGN",
        "UPTIME",
        "UPTIMESTAMP",
        "ACCOUNTCOMPANYID",
    ],
}

TEXT_SECRET_PATTERNS = {
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.+-])"),
    "access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b", re.IGNORECASE),
    "phone_like": re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){10,16}(?!\d)"),
    "oracle_endpoint": re.compile(r"\b(?:HOST|PORT|SERVICE_NAME|SID)\s*=", re.IGNORECASE),
}
FORBIDDEN_COLUMN_NAME_RE = re.compile(
    r"\b("
    + "|".join(re.escape(item) for item in sorted(SENSITIVE_COLUMNS | {"PASSWORD", "TOKEN", "USERNAME"}))
    + r")\b",
    re.IGNORECASE,
)
SAFE_PHONE_CONTEXT_KEYS = {
    "sha256",
    "removed_column_names_sha256",
    "duckdb_sha256",
    "original_prefix",
    "source_prefix",
    "prefix",
}


@dataclass(frozen=True)
class Artifact:
    path: Path
    role: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gzip_file(source: Path, target: Path) -> None:
    with source.open("rb") as src, target.open("wb") as raw_dst, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw_dst, compresslevel=9, mtime=0
    ) as dst:
        shutil.copyfileobj(src, dst)


def _hmac_function(key: bytes):
    def hash_value(value: Any) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        return hmac.new(key, raw.encode("utf-8"), hashlib.sha256).hexdigest()

    return hash_value


def _quote_name(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _source_ref(table: str) -> str:
    return f'src.{_quote_name(SOURCE_SCHEMA)}.{_quote_name(table)}'


def _target_ref(table: str) -> str:
    return f'{_quote_name(SOURCE_SCHEMA)}.{_quote_name(table)}'


def _select_expression(expression: str) -> str:
    if "(" in expression or " AS " in expression.upper():
        return expression
    return _quote_name(expression)


def _output_name(expression: str) -> str:
    match = re.search(r"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", expression, re.IGNORECASE)
    if match:
        return match.group(1)
    return expression


def _validate_allowlist(source: duckdb.DuckDBPyConnection) -> None:
    for table, expressions in ALLOWLIST.items():
        columns = {
            row[1].upper()
            for row in source.execute(f"PRAGMA table_info('{SOURCE_SCHEMA}.{table}')").fetchall()
        }
        missing: list[str] = []
        for expression in expressions:
            if "(" in expression or " AS " in expression.upper():
                continue
            if expression.upper() not in columns:
                missing.append(expression)
        if missing:
            raise RuntimeError(f"{table} allowlist references missing source columns: {missing}")


def _create_sanitized_duckdb(source_path: Path, target_path: Path, hmac_key: bytes) -> dict[str, Any]:
    if target_path.exists():
        target_path.unlink()
    con = duckdb.connect(str(target_path))
    con.execute("INSTALL json")
    con.execute("LOAD json")
    con.create_function("hmac_sha256", _hmac_function(hmac_key), return_type="VARCHAR", null_handling="special")
    con.execute(f"ATTACH {str(source_path)!r} AS src (READ_ONLY)")
    con.execute(f"CREATE SCHEMA {_quote_name(SOURCE_SCHEMA)}")
    source = duckdb.connect(str(source_path), read_only=True)
    _validate_allowlist(source)

    report: dict[str, Any] = {
        "tables": {},
        "removed_sensitive_column_count": 0,
        "removed_sensitive_column_categories": {
            "customer_direct_identifiers": 0,
            "contact_fields": 0,
            "staff_names": 0,
            "staff_identifiers_hmac_replaced": 0,
            "free_text_fields": 0,
        },
    }
    for table, expressions in ALLOWLIST.items():
        select_list = ", ".join(_select_expression(expression) for expression in expressions)
        con.execute(f"CREATE TABLE {_target_ref(table)} AS SELECT {select_list} FROM {_source_ref(table)}")
        source_columns = {
            row[1].upper()
            for row in source.execute(f"PRAGMA table_info('{SOURCE_SCHEMA}.{table}')").fetchall()
        }
        output_columns = [_output_name(expression).upper() for expression in expressions]
        removed = sorted(source_columns - set(output_columns))
        report["tables"][table] = {
            "rows": con.execute(f"SELECT count(*) FROM {_target_ref(table)}").fetchone()[0],
            "columns": output_columns,
            "removed_column_count": len(removed),
            "removed_column_names_sha256": hashlib.sha256(",".join(removed).encode("utf-8")).hexdigest(),
        }
        for column in removed:
            if column in DIRECT_IDENTIFIER_COLUMNS:
                report["removed_sensitive_column_categories"]["customer_direct_identifiers"] += 1
            elif column in CONTACT_COLUMNS:
                report["removed_sensitive_column_categories"]["contact_fields"] += 1
            elif column in STAFF_NAME_COLUMNS:
                report["removed_sensitive_column_categories"]["staff_names"] += 1
            elif column in STAFF_IDENTIFIER_COLUMNS:
                report["removed_sensitive_column_categories"]["staff_identifiers_hmac_replaced"] += 1
            elif column in FREE_TEXT_COLUMNS:
                report["removed_sensitive_column_categories"]["free_text_fields"] += 1
            if column in SENSITIVE_COLUMNS:
                report["removed_sensitive_column_count"] += 1
    con.execute("CHECKPOINT")
    con.close()
    source.close()
    return report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_metadata(out_dir: Path, privacy: dict[str, Any], duckdb_sha256: str) -> list[Artifact]:
    metadata_dir = out_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    validation = {
        "schema_version": "oracle.sales.validation.v1",
        "data_through": DATA_THROUGH,
        "relative_time_anchor": "max(SELLDATE)=2026-08-15",
        "row_counts": EXPECTED_ROW_COUNTS,
        "golden_queries": {
            "ticket_count_last_30_snapshot_days": {
                "filters": {
                    "CANCELSIGN": "N",
                    "STATUS": "002",
                    "SELLSTATEID": ["01", "02"],
                    "SELLDATE": ["2026-07-17", "2026-08-15"],
                },
                "expected": 86,
            },
            "top_3_stores_by_ticket_count": [
                {"store": "VNPTTE", "ticket_count": 56},
                {"store": "SG - ANTA VIVO City", "ticket_count": 9},
                {"store": "HARAVAN_ANTA_VN", "ticket_count": 5},
            ],
            "cross_country_sales_amount": {
                "status": "blocked",
                "reason": "Base currency is not confirmed for cross-country ACCOUNT_SALES aggregation.",
            },
            "customer_name_phone_query": {
                "policy_decision": "denied",
                "reason": "Direct customer identifiers are not available in the sanitized snapshot.",
            },
        },
        "gates": [
            "checksum",
            "pii",
            "enumeration_evidence",
            "key_uniqueness",
            "fanout",
            "orphan_records",
            "header_detail_reconciliation",
            "currency_unit",
            "sql_regression",
            "read_only_policy",
        ],
        "known_warnings": [
            "Employee dimension remains blocked until the composite key is resolved.",
            "Product analysis must warn about 899 unmatched detail rows until item coverage is resolved.",
        ],
        "duckdb_sha256": duckdb_sha256,
    }
    dictionary = {
        "schema_version": "oracle.sales.dictionary.v1",
        "source": "business dictionary evidence reconstructed for offline sanitized snapshot import",
        "enumerations": {
            "STATUS": {
                "001": "draft_or_incomplete",
                "002": "posted_valid",
            },
            "SELLSTATEID": {
                "00": "pending_or_unknown",
                "01": "normal_sale",
                "02": "normal_sale_confirmed",
                "04": "void_or_return_related",
                "05": "closed_or_exception",
            },
            "SELLTYPECODE": {
                "01": "retail_sale",
                "02": "return",
                "03": "exchange",
                "04": "other_adjustment",
            },
            "PROMOTIONSIGN": {"0": "not_promotional", "1": "promotional"},
            "GIFTSIGN": {"0": "not_gift", "1": "gift"},
        },
    }
    semantic_model = {
        "schema_version": "oracle.sales.semantic.v1",
        "provenance": {
            "source": "sanitized-from-snapshot",
            "original_prefix": ORIGINAL_PREFIX,
            "data_through": DATA_THROUGH,
        },
        "metrics": [
            {
                "id": "ticket_count",
                "name": "Ticket Count",
                "definition": "Count of distinct sales bill IDs for posted, non-cancelled tickets.",
                "formula": "count(distinct hd.BILLID)",
                "version": "v1",
                "grain": "ticket/header",
                "unit": "ticket",
                "approved": True,
            },
            {
                "id": "sales_amount",
                "name": "Sales Amount",
                "definition": "Header sales amount. Blocked for cross-country business KPI use until currency is confirmed.",
                "formula": "sum(hd.ACCOUNT_SALES)",
                "version": "v1",
                "grain": "ticket/header",
                "unit": "blocked_pending_currency_confirmation",
                "approved": False,
            },
        ],
        "dimensions": [
            {"id": "store", "field": "store.STORENAME"},
            {"id": "sell_date", "field": "hd.SELLDATE"},
            {"id": "sell_state", "field": "hd.SELLSTATEID"},
            {"id": "sell_type", "field": "hd.SELLTYPECODE"},
            {"id": "promotion", "field": "dt.PROMOTIONSIGN"},
            {"id": "gift", "field": "dt.GIFTSIGN"},
        ],
        "policy": {
            "deny_fields": ["direct_customer_identifiers", "contact_fields", "document_numbers"],
            "relative_time_anchor": "2026-08-15",
            "read_only": True,
        },
    }
    privacy_report = {
        "schema_version": "oracle.sales.privacy.v1",
        "source_status": "quarantined",
        "derived_snapshot_status": "sanitized",
        "provenance": "sanitized-from-snapshot",
        "removed_sensitive_column_count": privacy["removed_sensitive_column_count"],
        "removed_sensitive_column_categories": privacy["removed_sensitive_column_categories"],
        "hmac": {
            "algorithm": "HMAC-SHA256",
            "identifier_scope": "staff analytical joins only",
            "key_material": "runtime secret; not written to artifacts",
        },
    }
    files = {
        "validation_report.json": validation,
        "data_dictionary_evidence.json": dictionary,
        "semantic_model.json": semantic_model,
        "privacy_report.json": privacy_report,
        "schema_catalog.json": {
            "schema_version": "oracle.sales.schema_catalog.v2",
            "schema": SOURCE_SCHEMA,
            "tables": privacy["tables"],
        },
    }
    artifacts: list[Artifact] = []
    for name, payload in files.items():
        path = metadata_dir / name
        _write_json(path, payload)
        artifacts.append(Artifact(path=path, role=name.removesuffix(".json")))
    return artifacts


def _make_tar(source_dir: Path, target: Path) -> None:
    with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(source_dir))


def _scan_generated_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings = []
    if FORBIDDEN_COLUMN_NAME_RE.search(text):
        findings.append("forbidden sensitive column or credential field name")
    for label, pattern in TEXT_SECRET_PATTERNS.items():
        matches = [match for match in pattern.finditer(text) if not _is_safe_text_match_context(text, match.start())]
        if matches:
            findings.append(label)
    return findings


def _is_safe_text_match_context(text: str, offset: int) -> bool:
    left = text[max(0, offset - 96) : offset].lower()
    return any(f'"{key.lower()}"' in left or key.lower() in left for key in SAFE_PHONE_CONTEXT_KEYS)


def _scan_duckdb(path: Path) -> list[str]:
    findings: list[str] = []
    con = duckdb.connect(str(path), read_only=True)
    tables = con.execute(
        """
        select table_schema, table_name
        from information_schema.tables
        where table_schema not in ('information_schema', 'pg_catalog')
        order by table_schema, table_name
        """
    ).fetchall()
    for schema, table in tables:
        columns = con.execute(f"PRAGMA table_info('{schema}.{table}')").fetchall()
        for column in columns:
            name = str(column[1])
            data_type = str(column[2]).upper()
            if FORBIDDEN_COLUMN_NAME_RE.search(name):
                findings.append(f"{schema}.{table}.{name}: forbidden column name")
            if "VARCHAR" in data_type or "TEXT" in data_type:
                ref = f'{_quote_name(schema)}.{_quote_name(table)}'
                col = _quote_name(name)
                for label, pattern in TEXT_SECRET_PATTERNS.items():
                    sql_pattern = pattern.pattern.replace("'", "''")
                    try:
                        count = con.execute(
                            f"select count(*) from {ref} where regexp_matches(cast({col} as varchar), ?)",
                            [sql_pattern],
                        ).fetchone()[0]
                    except Exception:
                        count = 0
                    if count:
                        findings.append(f"{schema}.{table}.{name}: {label} ({count})")
    con.close()
    return findings


def _scan_tar_members(path: Path) -> list[str]:
    findings: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                findings.append(f"{member.name}: link member is not allowed")
            if Path(member.name).is_absolute() or ".." in Path(member.name).parts:
                findings.append(f"{member.name}: unsafe tar path")
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            text = extracted.read(1024 * 1024).decode("utf-8", errors="ignore")
            if FORBIDDEN_COLUMN_NAME_RE.search(text):
                findings.append(f"{member.name}: forbidden sensitive column or credential field name")
            for label, pattern in TEXT_SECRET_PATTERNS.items():
                if any(not _is_safe_text_match_context(text, match.start()) for match in pattern.finditer(text)):
                    findings.append(f"{member.name}: {label}")
    return findings


def _artifact_manifest(artifact: Artifact, out_dir: Path) -> dict[str, Any]:
    path = artifact.path
    return {
        "role": artifact.role,
        "path": str(path.relative_to(out_dir)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def generate_snapshot(source_duckdb: Path, output_root: Path, hmac_key: str, stamp: str | None = None) -> dict[str, Any]:
    if not source_duckdb.is_file():
        raise FileNotFoundError(source_duckdb)
    stamp = stamp or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    prefix = SANITIZED_PREFIX_TEMPLATE.format(stamp=stamp)
    out_dir = output_root / prefix
    if out_dir.exists():
        raise FileExistsError(f"Refusing to overwrite immutable snapshot directory: {out_dir}")
    out_dir.mkdir(parents=True)
    duckdb_path = out_dir / "local_oracle_sales_sanitized.duckdb"
    privacy = _create_sanitized_duckdb(source_duckdb, duckdb_path, hmac_key.encode("utf-8"))

    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        observed_counts = {
            table: con.execute(f"select count(*) from {_target_ref(table)}").fetchone()[0]
            for table in EXPECTED_ROW_COUNTS
        }
        max_sell_date = con.execute(f"select max(SELLDATE)::date from {_target_ref('P_BL_SELL_HD')}").fetchone()[0]
        gold_ticket_count = con.execute(
            f"""
            select count(distinct BILLID)
            from {_target_ref('P_BL_SELL_HD')}
            where CANCELSIGN='N'
              and STATUS='002'
              and SELLSTATEID in ('01','02')
              and SELLDATE >= date '2026-07-17'
              and SELLDATE <= date '2026-08-15'
            """
        ).fetchone()[0]
        top_stores = con.execute(
            f"""
            select coalesce(store.STORENAME, hd.STOREID) as store_name, count(distinct hd.BILLID) as ticket_count
            from {_target_ref('P_BL_SELL_HD')} hd
            left join {_target_ref('P_ARC_STORE')} store on hd.STOREID = store.STOREID
            where hd.CANCELSIGN='N'
              and hd.STATUS='002'
              and hd.SELLSTATEID in ('01','02')
              and hd.SELLDATE >= date '2026-07-17'
              and hd.SELLDATE <= date '2026-08-15'
            group by 1
            order by ticket_count desc, store_name asc
            limit 3
            """
        ).fetchall()

    if observed_counts != EXPECTED_ROW_COUNTS:
        raise RuntimeError(f"Row-count regression: expected {EXPECTED_ROW_COUNTS}, observed {observed_counts}")
    if str(max_sell_date) != DATA_THROUGH:
        raise RuntimeError(f"Unexpected data-through date: {max_sell_date}")
    if gold_ticket_count != 86:
        raise RuntimeError(f"Gold ticket-count regression: {gold_ticket_count}")
    if top_stores != [("VNPTTE", 56), ("SG - ANTA VIVO City", 9), ("HARAVAN_ANTA_VN", 5)]:
        raise RuntimeError(f"Gold Top 3 store regression: {top_stores}")

    duckdb_gz = out_dir / "local_oracle_sales_sanitized.duckdb.gz"
    _gzip_file(duckdb_path, duckdb_gz)
    metadata_artifacts = _write_metadata(out_dir, privacy, _sha256(duckdb_path))
    metadata_tar = out_dir / "oracle_local_extract_sanitized_metadata_only.tar.gz"
    _make_tar(out_dir / "metadata", metadata_tar)

    scan_findings = []
    scan_findings.extend(f"duckdb: {finding}" for finding in _scan_duckdb(duckdb_path))
    for artifact in metadata_artifacts:
        scan_findings.extend(f"{artifact.path.name}: {finding}" for finding in _scan_generated_text(artifact.path))
    scan_findings.extend(f"metadata_tar: {finding}" for finding in _scan_tar_members(metadata_tar))
    if scan_findings:
        raise RuntimeError("Sanitized snapshot privacy scan failed: " + "; ".join(scan_findings))

    manifest_artifacts = [
        Artifact(path=duckdb_gz, role="sanitized_duckdb_gzip"),
        Artifact(path=metadata_tar, role="sanitized_metadata_tar_gzip"),
        *metadata_artifacts,
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "prefix": prefix,
        "source_prefix_status": "quarantined_revoke_access_required",
        "source_prefix": ORIGINAL_PREFIX,
        "provenance": "sanitized-from-snapshot",
        "extracted_at": datetime.now(UTC).isoformat(),
        "data_through": DATA_THROUGH,
        "privacy_report": "metadata/privacy_report.json",
        "row_counts": observed_counts,
        "golden_results": {
            "relative_time_anchor": "max(SELLDATE)=2026-08-15",
            "ticket_count_last_30_snapshot_days": gold_ticket_count,
            "top_3_stores_by_ticket_count": [
                {"store": name, "ticket_count": count} for name, count in top_stores
            ],
            "customer_name_phone_policy": "denied",
            "cross_country_sales_amount": "blocked_pending_currency_confirmation",
        },
        "business_artifacts": [_artifact_manifest(artifact, out_dir) for artifact in manifest_artifacts],
        "uncompressed_duckdb": {
            "path": duckdb_path.name,
            "bytes": duckdb_path.stat().st_size,
            "sha256": _sha256(duckdb_path),
        },
    }
    manifest_path = out_dir / "upload_manifest_v2.json"
    _write_json(manifest_path, manifest)
    return {"output_dir": str(out_dir), "manifest_path": str(manifest_path), "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a sanitized Oracle sales snapshot from a quarantined DuckDB.")
    parser.add_argument("--source-duckdb", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--stamp", default=None)
    parser.add_argument(
        "--hmac-key-env",
        default="ORACLE_SNAPSHOT_HMAC_KEY",
        help="Environment variable containing the HMAC key for retained analytical identifiers.",
    )
    args = parser.parse_args()
    hmac_key = os.getenv(args.hmac_key_env, "")
    if len(hmac_key) < 32:
        raise SystemExit(f"{args.hmac_key_env} must be set to at least 32 characters")
    result = generate_snapshot(args.source_duckdb, args.output_root, hmac_key=hmac_key, stamp=args.stamp)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
