from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from server.services.duckdb_service import DuckDBService
from server.scripts.oracle_snapshot_sanitizer import (
    DIRECT_IDENTIFIER_COLUMNS,
    EXPECTED_ROW_COUNTS,
    SOURCE_SCHEMA,
    generate_snapshot,
    _scan_generated_text,
)


def _create_source(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute(f'create schema "{SOURCE_SCHEMA}"')
    con.execute(
        f'''
        create table "{SOURCE_SCHEMA}"."P_BL_SELL_HD" as
        select
          1::bigint SERIES,
          'B1'::varchar BILLID,
          'VNPTTE'::varchar STOREID,
          'P1'::varchar POSID,
          timestamp '2026-08-15 09:00:00' OPERATETIME,
          100.00::decimal(18,2) ACCOUNT_SALES,
          'member'::varchar CUST_TYPE,
          123::decimal(20,0) CUST_ID,
          'Jane Doe'::varchar CUST_NAME,
          timestamp '2026-08-15 00:00:00' SELLDATE,
          '09:00:00'::varchar SELLTIME,
          0.00::decimal(18,2) DEDUCTIBLE_AMOUNT,
          100.00::decimal(18,2) ACCOUNT_PAID,
          0.00::decimal(18,2) ODD_CHANGE,
          'S1'::varchar STAFFID,
          '01'::varchar SELLSTATEID,
          '01'::varchar SELLTYPECODE,
          null::varchar OLDBILLIDID,
          100.00::decimal(18,2) ACCOUNT_PAYABLE,
          'D1'::varchar SELLDAILYID,
          'customer phone 15500000000'::varchar REMARK,
          'N'::varchar CANCELSIGN,
          'N'::varchar POSINPUTSIGN,
          'N'::varchar MAKE_POINT_SIGN,
          0.00::decimal(18,2) CUST_POINT,
          0.00::decimal(16,2) WIPE_ZERO,
          'offline'::varchar SALESMODE,
          'VIP1'::varchar VIPID,
          'O1'::varchar ORDERFORMID,
          'N'::varchar MAKEDKCOSTSIGN,
          '1 Main St'::varchar CUST_ADDR,
          timestamp '2026-08-15 00:00:00' POST_DATE,
          'Y'::varchar POST_FLAG,
          timestamp '2026-08-15 00:00:00' IMPORT_DATE,
          'Y'::varchar IMPORT_FLAG,
          timestamp '2026-08-15 00:00:00' INACCOUNT_DATE,
          'WH1'::varchar STORAGEID,
          timestamp '2026-08-15 00:00:00' FACT_PICK_GOOD_DATE,
          'Y'::varchar PICK_FLAG,
          'N'::varchar RETURN_GOODS_ATTR,
          '15500000000'::varchar CUST_TEL,
          'VIPCX'::varchar VIPCXID,
          timestamp '2026-08-15 00:00:00' UPTIME,
          'U1'::varchar UPSTAFF,
          1::bigint QTY,
          'BANK1'::varchar BANKPAYID,
          '002'::varchar STATUS,
          'S2'::varchar INACCOUNT_STAFF,
          0::bigint VIPJF,
          'N'::varchar INVSTATUS,
          null::varchar INVBILLID,
          null::varchar SCHDBILLID,
          timestamp '2026-08-15 00:00:00' UPTIMESTAMP,
          0.00::decimal(16,4) DISCOUNTAMOUNT,
          null::varchar ZKBILLID,
          null::varchar ZKTYPE,
          'C1'::varchar ACCOUNTCOMPANYID,
          'N'::varchar SYNSIGN,
          timestamp '2026-08-15 00:00:00' SYNTIME,
          'N'::varchar IMPORTSIGN,
          'N'::varchar DSTSYNSIGN,
          timestamp '2026-08-15 00:00:00' DSTSYNTIME,
          'N'::varchar BISYNSIGN,
          timestamp '2026-08-15 00:00:00' PRESELLDATE,
          'done'::varchar WORKSTATUS,
          'N'::varchar SYSYNSIGN,
          timestamp '2026-08-15 00:00:00' SYSYNTIME,
          'retail'::varchar SALESTYPE,
          0.00::decimal(18,4) VATRATE,
          0.00::decimal(18,2) VAT,
          100.00::decimal(18,2) NET,
          100.00::decimal(18,2) BASEACCOUNT_SALES,
          100.00::decimal(18,2) BASEACCOUNT_PAID,
          0.00::decimal(18,2) BASEODD_CHANGE,
          100.00::decimal(18,2) BASEACCOUNT_PAYABLE,
          0.00::decimal(16,2) BASEWIPE_ZERO,
          0.00::decimal(18,2) BASEVAT,
          100.00::decimal(18,2) BASENET,
          'CARD1'::varchar MARKETVIPCARDNO,
          'Y'::varchar SHOWSIGN,
          'N'::varchar FREESHIPSIGN,
          null::varchar FRSTORE,
          'N'::varchar PARTRETURNLIMIT,
          null::varchar SELLERTAX,
          'BP'::varchar BOARDINGPASS,
          'PP'::varchar PASSPORT,
          'free text'::varchar FJ
        '''
    )
    con.execute(f'create table "{SOURCE_SCHEMA}"."P_BL_SELL_DT" as select * from "{SOURCE_SCHEMA}"."P_BL_SELL_HD" limit 0')
    con.close()


def test_expected_row_count_contract_is_the_real_oracle_snapshot_contract() -> None:
    assert list(EXPECTED_ROW_COUNTS.values()) == [4279, 7006, 433, 818856, 300, 17, 352, 447]


def test_direct_customer_columns_are_classified_sensitive() -> None:
    assert {"CUST_NAME", "CUST_ADDR", "CUST_TEL", "MARKETVIPCARDNO", "PASSPORT"}.issubset(
        DIRECT_IDENTIFIER_COLUMNS
    )


def test_generate_snapshot_refuses_to_overwrite_immutable_prefix(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.duckdb"
    _create_source(source)
    monkeypatch.setitem(EXPECTED_ROW_COUNTS, "P_BL_SELL_HD", 1)
    for key in list(EXPECTED_ROW_COUNTS):
        if key != "P_BL_SELL_HD":
            monkeypatch.setitem(EXPECTED_ROW_COUNTS, key, 0)

    # The source is intentionally incomplete, so generation fails before writing a successful manifest.
    try:
        generate_snapshot(source, tmp_path, hmac_key="x" * 32, stamp="unit")
    except Exception:
        pass

    (tmp_path / "oracle-local-extract-sanitized" / "unit-arkclaw").mkdir(parents=True, exist_ok=True)
    try:
        generate_snapshot(source, tmp_path, hmac_key="x" * 32, stamp="unit")
    except FileExistsError as error:
        assert "Refusing to overwrite" in str(error)
    else:
        raise AssertionError("expected immutable prefix protection")


def test_generated_text_scan_allows_hashes_and_prefix_dates_but_blocks_sensitive_fields(tmp_path: Path) -> None:
    clean = tmp_path / "clean.json"
    clean.write_text(
        json.dumps(
            {
                "sha256": "f6b333f274677905d3f38d3ffc7c07c52a32cc836b865639161577bb4e618f18",
                "original_prefix": "oracle-local-extract/20260817-114544-arkclaw",
                "key_material": "runtime secret; not written to artifacts",
            }
        )
    )
    assert _scan_generated_text(clean) == []

    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps({"columns": ["CUST_NAME"], "sample": "15500000000"}))
    findings = _scan_generated_text(dirty)
    assert "forbidden sensitive column or credential field name" in findings
    assert "phone_like" in findings


@pytest.mark.asyncio
async def test_duckdb_service_queries_existing_catalog_without_file_descriptors(tmp_path: Path) -> None:
    db_path = tmp_path / "oracle.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute('create schema "dnyxlstest"')
    con.execute(
        '''
        create table dnyxlstest.P_BL_SELL_HD as
        select 'B1'::varchar BILLID, 'VNPTTE'::varchar STOREID, date '2026-08-15' SELLDATE,
               'N'::varchar CANCELSIGN, '002'::varchar STATUS, '01'::varchar SELLSTATEID
        '''
    )
    con.close()

    result = await DuckDBService.execute_sql(
        [],
        '''
        select count(distinct BILLID) ticket_count
        from dnyxlstest.P_BL_SELL_HD
        where CANCELSIGN = 'N' and STATUS = '002' and SELLSTATEID in ('01', '02')
        ''',
        database_path=db_path,
    )

    assert result["success"] is True
    assert result["result"] == [{"ticket_count": 1}]
