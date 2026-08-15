from __future__ import annotations

import json
import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.models.semantic_models import (
    SemanticModel,
    SemanticModelAuditEvent,
    SemanticModelCalculatedField,
    SemanticModelConsumer,
    SemanticModelDimension,
    SemanticModelEntity,
    SemanticModelField,
    SemanticModelGenerationJob,
    SemanticModelMetric,
    SemanticModelPublication,
    SemanticModelRelationship,
    SemanticModelSuggestion,
    SemanticModelValidationResult,
    SemanticModelVersion,
)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return deepcopy(fallback)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return deepcopy(fallback)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _now_label() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M")


_SEED_LOCKS: dict[str, asyncio.Lock] = {}


def _seed_lock(tenant_id: UUID) -> asyncio.Lock:
    key = str(tenant_id)
    lock = _SEED_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SEED_LOCKS[key] = lock
    return lock


SALES_TABLES: list[dict[str, Any]] = [
    {
        "name": "ORDERS",
        "label": "Orders",
        "category": "fact",
        "rowCount": 1248930,
        "timeRange": "2024-01-01 to 2026-08-12",
        "fields": [
            {
                "name": "ORDER_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 1248930,
                "min": 1000001,
                "max": 2248931,
                "topValues": [],
                "pii": False,
            },
            {
                "name": "CUSTOMER_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 241804,
                "topValues": [{"value": "928104", "count": 18}, {"value": "341912", "count": 16}],
                "pii": False,
            },
            {
                "name": "STORE_ID",
                "type": "NUMBER(10)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 184,
                "topValues": [{"value": "S-018", "count": 19421}, {"value": "S-044", "count": 18877}],
                "pii": False,
            },
            {
                "name": "ORDER_STATUS",
                "type": "VARCHAR2(32)",
                "role": "status",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 6,
                "topValues": [{"value": "PAID", "count": 891204}, {"value": "REFUNDED", "count": 44102}],
                "pii": False,
            },
            {
                "name": "ORDER_DATE",
                "type": "DATE",
                "role": "time",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 956,
                "min": "2024-01-01",
                "max": "2026-08-12",
                "topValues": [],
                "pii": False,
            },
            {
                "name": "PAID_AT",
                "type": "TIMESTAMP",
                "role": "time",
                "nullable": True,
                "nullRate": 7.8,
                "distinctCount": 1112803,
                "min": "2024-01-01 00:13",
                "max": "2026-08-12 23:57",
                "topValues": [],
                "pii": False,
            },
            {
                "name": "NET_AMOUNT",
                "type": "NUMBER(18,2)",
                "role": "amount",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 43208,
                "min": 0,
                "max": 24080.5,
                "topValues": [{"value": "99.00", "count": 58122}, {"value": "129.00", "count": 49310}],
                "pii": False,
            },
        ],
        "sampleRows": [
            {
                "ORDER_ID": 2248120,
                "CUSTOMER_ID": 809122,
                "STORE_ID": 18,
                "ORDER_STATUS": "PAID",
                "ORDER_DATE": "2026-08-12",
                "NET_AMOUNT": 328.9,
            },
            {
                "ORDER_ID": 2248121,
                "CUSTOMER_ID": 381022,
                "STORE_ID": 44,
                "ORDER_STATUS": "REFUNDED",
                "ORDER_DATE": "2026-08-12",
                "NET_AMOUNT": 89.0,
            },
        ],
    },
    {
        "name": "ORDER_ITEMS",
        "label": "Order Items",
        "category": "bridge",
        "rowCount": 3894408,
        "timeRange": "2024-01-01 to 2026-08-12",
        "fields": [
            {
                "name": "ORDER_ITEM_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 3894408,
                "topValues": [],
                "pii": False,
            },
            {
                "name": "ORDER_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 1248930,
                "topValues": [],
                "pii": False,
            },
            {
                "name": "PRODUCT_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 12980,
                "topValues": [{"value": "P-8218", "count": 11802}],
                "pii": False,
            },
            {
                "name": "QUANTITY",
                "type": "NUMBER(10)",
                "role": "measure",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 19,
                "min": 1,
                "max": 48,
                "topValues": [{"value": "1", "count": 2711112}, {"value": "2", "count": 701908}],
                "pii": False,
            },
            {
                "name": "ITEM_REVENUE",
                "type": "NUMBER(18,2)",
                "role": "amount",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 80422,
                "min": 0,
                "max": 12999,
                "topValues": [{"value": "49.00", "count": 190223}],
                "pii": False,
            },
        ],
        "sampleRows": [
            {"ORDER_ITEM_ID": 7783011, "ORDER_ID": 2248120, "PRODUCT_ID": 8218, "QUANTITY": 2, "ITEM_REVENUE": 258.0},
            {"ORDER_ITEM_ID": 7783012, "ORDER_ID": 2248120, "PRODUCT_ID": 1920, "QUANTITY": 1, "ITEM_REVENUE": 70.9},
        ],
    },
    {
        "name": "CUSTOMERS",
        "label": "Customers",
        "category": "dimension",
        "rowCount": 241804,
        "fields": [
            {
                "name": "CUSTOMER_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 241804,
                "topValues": [],
                "pii": False,
            },
            {
                "name": "CUSTOMER_TIER",
                "type": "VARCHAR2(24)",
                "role": "attribute",
                "nullable": True,
                "nullRate": 4.1,
                "distinctCount": 5,
                "topValues": [{"value": "Gold", "count": 80221}, {"value": "Silver", "count": 73008}],
                "pii": False,
            },
            {
                "name": "EMAIL",
                "type": "VARCHAR2(255)",
                "role": "pii",
                "nullable": True,
                "nullRate": 9.5,
                "distinctCount": 219018,
                "topValues": [],
                "pii": True,
            },
            {
                "name": "PHONE",
                "type": "VARCHAR2(64)",
                "role": "pii",
                "nullable": True,
                "nullRate": 16.2,
                "distinctCount": 201441,
                "topValues": [],
                "pii": True,
            },
            {
                "name": "CREATED_AT",
                "type": "DATE",
                "role": "time",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 2140,
                "min": "2020-03-18",
                "max": "2026-08-12",
                "topValues": [],
                "pii": False,
            },
        ],
        "sampleRows": [
            {
                "CUSTOMER_ID": 809122,
                "CUSTOMER_TIER": "Gold",
                "EMAIL": "masked@example.com",
                "PHONE": "masked",
                "CREATED_AT": "2024-11-08",
            },
            {
                "CUSTOMER_ID": 381022,
                "CUSTOMER_TIER": "Silver",
                "EMAIL": "masked@example.com",
                "PHONE": "masked",
                "CREATED_AT": "2023-05-19",
            },
        ],
    },
    {
        "name": "PRODUCTS",
        "label": "Products",
        "category": "dimension",
        "rowCount": 12980,
        "fields": [
            {"name": "PRODUCT_ID", "type": "NUMBER(18)", "role": "id", "nullable": False, "nullRate": 0, "distinctCount": 12980, "topValues": [], "pii": False},
            {
                "name": "CATEGORY",
                "type": "VARCHAR2(64)",
                "role": "attribute",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 28,
                "topValues": [{"value": "Consumer Electronics", "count": 2240}, {"value": "Home", "count": 1788}],
                "pii": False,
            },
            {
                "name": "BRAND",
                "type": "VARCHAR2(64)",
                "role": "attribute",
                "nullable": True,
                "nullRate": 2.9,
                "distinctCount": 441,
                "topValues": [{"value": "Northline", "count": 402}, {"value": "Civic", "count": 388}],
                "pii": False,
            },
            {
                "name": "LIST_PRICE",
                "type": "NUMBER(18,2)",
                "role": "amount",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 2140,
                "min": 5.9,
                "max": 19999,
                "topValues": [{"value": "99.00", "count": 392}],
                "pii": False,
            },
        ],
        "sampleRows": [
            {"PRODUCT_ID": 8218, "CATEGORY": "Consumer Electronics", "BRAND": "Northline", "LIST_PRICE": 129.0},
            {"PRODUCT_ID": 1920, "CATEGORY": "Home", "BRAND": "Civic", "LIST_PRICE": 70.9},
        ],
    },
    {
        "name": "STORES",
        "label": "Stores",
        "category": "dimension",
        "rowCount": 184,
        "fields": [
            {"name": "STORE_ID", "type": "NUMBER(10)", "role": "id", "nullable": False, "nullRate": 0, "distinctCount": 184, "topValues": [], "pii": False},
            {
                "name": "REGION",
                "type": "VARCHAR2(32)",
                "role": "attribute",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 7,
                "topValues": [{"value": "East", "count": 42}, {"value": "South", "count": 39}],
                "pii": False,
            },
            {
                "name": "STORE_FORMAT",
                "type": "VARCHAR2(32)",
                "role": "attribute",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 4,
                "topValues": [{"value": "Flagship", "count": 41}, {"value": "Mall", "count": 68}],
                "pii": False,
            },
        ],
        "sampleRows": [
            {"STORE_ID": 18, "REGION": "East", "STORE_FORMAT": "Flagship"},
            {"STORE_ID": 44, "REGION": "South", "STORE_FORMAT": "Mall"},
        ],
    },
    {
        "name": "REFUNDS",
        "label": "Refunds",
        "category": "log",
        "rowCount": 58320,
        "timeRange": "2024-01-02 to 2026-08-12",
        "fields": [
            {"name": "REFUND_ID", "type": "NUMBER(18)", "role": "id", "nullable": False, "nullRate": 0, "distinctCount": 58320, "topValues": [], "pii": False},
            {
                "name": "ORDER_ID",
                "type": "NUMBER(18)",
                "role": "id",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 44102,
                "topValues": [{"value": "2190041", "count": 4}],
                "pii": False,
            },
            {
                "name": "REFUND_AMOUNT",
                "type": "NUMBER(18,2)",
                "role": "amount",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 18102,
                "min": 1,
                "max": 9031.4,
                "topValues": [{"value": "29.00", "count": 992}],
                "pii": False,
            },
            {
                "name": "REFUNDED_AT",
                "type": "TIMESTAMP",
                "role": "time",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 58110,
                "min": "2024-01-02",
                "max": "2026-08-12",
                "topValues": [],
                "pii": False,
            },
            {
                "name": "REASON_CODE",
                "type": "VARCHAR2(32)",
                "role": "status",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 12,
                "topValues": [{"value": "DAMAGED", "count": 12144}, {"value": "LATE_DELIVERY", "count": 8220}],
                "pii": False,
            },
        ],
        "sampleRows": [
            {"REFUND_ID": 92110, "ORDER_ID": 2248121, "REFUND_AMOUNT": 89, "REFUNDED_AT": "2026-08-12", "REASON_CODE": "DAMAGED"},
            {"REFUND_ID": 92111, "ORDER_ID": 2247002, "REFUND_AMOUNT": 41.5, "REFUNDED_AT": "2026-08-12", "REASON_CODE": "LATE_DELIVERY"},
        ],
    },
    {
        "name": "CHANNELS",
        "label": "Channels",
        "category": "dimension",
        "rowCount": 12,
        "fields": [
            {"name": "CHANNEL_ID", "type": "NUMBER(10)", "role": "id", "nullable": False, "nullRate": 0, "distinctCount": 12, "topValues": [], "pii": False},
            {
                "name": "CHANNEL_NAME",
                "type": "VARCHAR2(32)",
                "role": "attribute",
                "nullable": False,
                "nullRate": 0,
                "distinctCount": 12,
                "topValues": [{"value": "Marketplace", "count": 1}, {"value": "Retail", "count": 1}],
                "pii": False,
            },
        ],
        "sampleRows": [{"CHANNEL_ID": 1, "CHANNEL_NAME": "Retail"}, {"CHANNEL_ID": 2, "CHANNEL_NAME": "Marketplace"}],
    },
    {
        "name": "SALES_TARGETS",
        "label": "Sales Targets",
        "category": "fact",
        "rowCount": 4416,
        "timeRange": "2024-01 to 2026-12",
        "fields": [
            {"name": "STORE_ID", "type": "NUMBER(10)", "role": "id", "nullable": False, "nullRate": 0, "distinctCount": 184, "topValues": [], "pii": False},
            {"name": "TARGET_MONTH", "type": "DATE", "role": "time", "nullable": False, "nullRate": 0, "distinctCount": 36, "min": "2024-01-01", "max": "2026-12-01", "topValues": [], "pii": False},
            {"name": "REVENUE_TARGET", "type": "NUMBER(18,2)", "role": "amount", "nullable": False, "nullRate": 0, "distinctCount": 3180, "min": 40000, "max": 880000, "topValues": [], "pii": False},
        ],
        "sampleRows": [
            {"STORE_ID": 18, "TARGET_MONTH": "2026-08-01", "REVENUE_TARGET": 740000},
            {"STORE_ID": 44, "TARGET_MONTH": "2026-08-01", "REVENUE_TARGET": 520000},
        ],
    },
]


DEFAULT_PROFILE = {
    "id": "oracle-sales",
    "name": "Oracle SALES",
    "kind": "oracle",
    "schema": "SALES",
    "status": "ready",
    "profileCoverage": 94,
    "tables": SALES_TABLES,
}


GENERATION_STEPS = [
    {"id": "scan", "title": "Summarizing schema", "detail": "Read table metadata, sample rows, and persisted column profiles."},
    {"id": "fact", "title": "Classifying tables", "detail": "ORDERS is the core fact table; ORDER_ITEMS is line-item grain."},
    {"id": "relationships", "title": "Inferring relationships", "detail": "FK coverage and cardinality are checked from persisted profile evidence."},
    {"id": "fields", "title": "Generating field descriptions", "detail": "Money, time, status, ID, and PII roles are inferred."},
    {"id": "metrics", "title": "Suggesting metrics", "detail": "Paid Revenue, Order Count, AOV, Refund Rate, and Store Attainment are drafted."},
    {"id": "dimensions", "title": "Suggesting dimensions", "detail": "Region, Channel, Category, Store Format, Customer Tier, and Refund Reason are exposed."},
    {"id": "validation", "title": "Validating SQL", "detail": "Compile checks and fanout detection are run against the semantic contract."},
    {"id": "questions", "title": "Generating sample questions", "detail": "Confirmed examples are prepared for Explore and Agent readiness."},
]


RELATIONSHIPS = [
    {
        "id": "rel-orders-customers",
        "fromEntity": "customers",
        "toEntity": "orders",
        "label": "Customers -> Orders",
        "joinFields": [{"from": "CUSTOMERS.CUSTOMER_ID", "to": "ORDERS.CUSTOMER_ID"}],
        "cardinality": "one-to-many",
        "fkEvidence": "Profiled FK match 99.6%",
        "uniqueRate": 100,
        "orphanRate": 0.4,
        "fanoutRisk": "low",
        "validationStatus": "valid",
        "status": "confirmed",
        "validationMessage": "Validated against 50k sampled orders.",
    },
    {
        "id": "rel-orders-stores",
        "fromEntity": "stores",
        "toEntity": "orders",
        "label": "Stores -> Orders",
        "joinFields": [{"from": "STORES.STORE_ID", "to": "ORDERS.STORE_ID"}],
        "cardinality": "one-to-many",
        "fkEvidence": "STORE_ID profile aligns with STORES primary key.",
        "uniqueRate": 100,
        "orphanRate": 0,
        "fanoutRisk": "low",
        "validationStatus": "valid",
        "status": "confirmed",
        "validationMessage": "No orphaned store references detected.",
    },
    {
        "id": "rel-orders-items",
        "fromEntity": "orders",
        "toEntity": "order_items",
        "label": "Orders -> Order Items",
        "joinFields": [{"from": "ORDERS.ORDER_ID", "to": "ORDER_ITEMS.ORDER_ID"}],
        "cardinality": "one-to-many",
        "fkEvidence": "ORDER_ITEMS.ORDER_ID resolves to ORDERS.ORDER_ID in the profile sample.",
        "uniqueRate": 99.8,
        "orphanRate": 0.2,
        "fanoutRisk": "low",
        "validationStatus": "valid",
        "status": "confirmed",
        "validationMessage": "Validated as order header to line-item grain.",
    },
    {
        "id": "rel-items-products",
        "fromEntity": "order_items",
        "toEntity": "products",
        "label": "Order Items -> Products",
        "joinFields": [{"from": "ORDER_ITEMS.PRODUCT_ID", "to": "PRODUCTS.PRODUCT_ID"}],
        "cardinality": "many-to-one",
        "fkEvidence": "PRODUCT_ID has 99.9% reference coverage.",
        "uniqueRate": 100,
        "orphanRate": 0.1,
        "fanoutRisk": "low",
        "validationStatus": "valid",
        "status": "confirmed",
        "validationMessage": "Validated without measurable fanout.",
    },
    {
        "id": "rel-orders-refunds-risk",
        "fromEntity": "refunds",
        "toEntity": "orders",
        "label": "Refunds -> Orders candidate",
        "joinFields": [{"from": "REFUNDS.ORDER_ID", "to": "ORDERS.ORDER_ID"}],
        "cardinality": "many-to-many",
        "fkEvidence": "Some orders have multiple partial refunds.",
        "uniqueRate": 61.2,
        "orphanRate": 12.4,
        "fanoutRisk": "high",
        "validationStatus": "blocked",
        "status": "candidate",
        "validationMessage": "High fanout risk: aggregate REFUNDS by ORDER_ID before joining to order-level metrics.",
    },
    {
        "id": "rel-orders-channels",
        "fromEntity": "channels",
        "toEntity": "orders",
        "label": "Channels -> Orders",
        "joinFields": [{"from": "CHANNELS.CHANNEL_ID", "to": "ORDERS.CHANNEL_ID"}],
        "cardinality": "one-to-many",
        "fkEvidence": "CHANNEL_ID has low cardinality and matches known sales channel codes.",
        "uniqueRate": 100,
        "orphanRate": 0.2,
        "fanoutRisk": "low",
        "validationStatus": "valid",
        "status": "confirmed",
        "validationMessage": "Validated against sampled order acquisition channels.",
    },
]


METRICS = [
    {
        "id": "paid_revenue",
        "name": "paid_revenue",
        "businessName": "Paid Revenue",
        "definition": "Revenue from paid orders after discounts and before refunds.",
        "kind": "measure",
        "formula": "SUM(orders.net_amount)",
        "filter": "orders.order_status = 'PAID'",
        "timeField": "orders.paid_at",
        "defaultGrain": "month",
        "dimensions": ["order_month", "region", "channel", "category"],
        "unit": "USD",
        "owner": "Revenue Analytics",
        "certification": "reviewed",
        "lineage": ["ORDERS.NET_AMOUNT", "ORDERS.ORDER_STATUS", "ORDERS.PAID_AT"],
        "preview": {
            "currentValue": "$8.42M",
            "trend": "+12.8% vs prior period",
            "breakdown": [
                {"label": "East", "value": "$2.4M", "delta": "+9.1%"},
                {"label": "South", "value": "$1.9M", "delta": "+14.2%"},
                {"label": "West", "value": "$1.6M", "delta": "+6.4%"},
            ],
            "explanation": "Filters ORDERS to PAID rows, sums NET_AMOUNT, and groups by the selected time grain.",
            "sql": "SELECT DATE_TRUNC('month', paid_at) AS month, SUM(net_amount) AS paid_revenue FROM sales.orders WHERE order_status = 'PAID' GROUP BY 1",
            "validation": "Compiled SQL matched sample notebook result within 0.4%.",
        },
    },
    {
        "id": "order_count",
        "name": "order_count",
        "businessName": "Order Count",
        "definition": "Number of submitted orders.",
        "kind": "measure",
        "formula": "COUNT_DISTINCT(orders.order_id)",
        "filter": "orders.order_status IN ('PAID', 'REFUNDED', 'SHIPPED')",
        "timeField": "orders.order_date",
        "defaultGrain": "month",
        "dimensions": ["order_month", "region", "channel"],
        "unit": "orders",
        "owner": "Commerce Ops",
        "certification": "certified",
        "lineage": ["ORDERS.ORDER_ID", "ORDERS.ORDER_STATUS"],
        "preview": {
            "currentValue": "312,480",
            "trend": "+5.6% vs prior period",
            "breakdown": [
                {"label": "Retail", "value": "118,204", "delta": "+3.2%"},
                {"label": "Marketplace", "value": "96,440", "delta": "+11.0%"},
                {"label": "Wholesale", "value": "48,911", "delta": "-1.5%"},
            ],
            "explanation": "Counts unique ORDER_ID values after excluding canceled draft orders.",
            "sql": "SELECT COUNT(DISTINCT order_id) AS order_count FROM sales.orders WHERE order_status IN ('PAID', 'REFUNDED', 'SHIPPED')",
            "validation": "Certified against finance daily order audit.",
        },
    },
    {
        "id": "avg_order_value",
        "name": "avg_order_value",
        "businessName": "Average Order Value",
        "definition": "Paid revenue divided by paid order count.",
        "kind": "derived_metric",
        "formula": "paid_revenue / order_count",
        "filter": "orders.order_status = 'PAID'",
        "timeField": "orders.paid_at",
        "defaultGrain": "month",
        "dimensions": ["region", "channel", "customer_tier"],
        "unit": "USD/order",
        "owner": "Revenue Analytics",
        "certification": "reviewed",
        "lineage": ["paid_revenue", "order_count"],
        "preview": {
            "currentValue": "$73.24",
            "trend": "+2.4% vs prior period",
            "breakdown": [
                {"label": "Gold", "value": "$91.10", "delta": "+4.5%"},
                {"label": "Silver", "value": "$70.42", "delta": "+1.8%"},
                {"label": "Bronze", "value": "$54.18", "delta": "-0.6%"},
            ],
            "explanation": "Uses the same paid-order filter as Paid Revenue and divides by distinct paid orders.",
            "sql": "SELECT SUM(net_amount) / COUNT(DISTINCT order_id) AS avg_order_value FROM sales.orders WHERE order_status = 'PAID'",
            "validation": "No divide-by-zero buckets detected for selected dimensions.",
        },
    },
    {
        "id": "refund_rate",
        "name": "refund_rate",
        "businessName": "Refund Rate",
        "definition": "Refunded amount as a percentage of paid revenue.",
        "kind": "derived_metric",
        "formula": "SUM(refunds.refund_amount) / paid_revenue",
        "filter": "refunds.reason_code IS NOT NULL",
        "timeField": "refunds.refunded_at",
        "defaultGrain": "month",
        "dimensions": ["region", "category", "reason_code"],
        "unit": "%",
        "owner": "Commerce Ops",
        "certification": "draft",
        "lineage": ["REFUNDS.REFUND_AMOUNT", "paid_revenue"],
        "preview": {
            "currentValue": "4.8%",
            "trend": "+0.6 pts vs prior period",
            "breakdown": [
                {"label": "Damaged", "value": "1.6%", "delta": "+0.2 pts"},
                {"label": "Late delivery", "value": "1.1%", "delta": "+0.1 pts"},
                {"label": "Changed mind", "value": "0.9%", "delta": "-0.1 pts"},
            ],
            "explanation": "Aggregates refunds separately before comparing with paid revenue to avoid order fanout.",
            "sql": "WITH refund_by_order AS (...) SELECT SUM(refund_amount) / SUM(paid_revenue) AS refund_rate FROM modeled_orders",
            "validation": "Blocked until Orders -> Refunds candidate is fixed or rejected.",
        },
    },
    {
        "id": "store_attainment",
        "name": "store_attainment",
        "businessName": "Store Attainment Rate",
        "definition": "Paid revenue divided by monthly store revenue targets.",
        "kind": "derived_metric",
        "formula": "paid_revenue / SUM(sales_targets.revenue_target)",
        "filter": "sales_targets.target_month = DATE_TRUNC(month, orders.paid_at)",
        "timeField": "orders.paid_at",
        "defaultGrain": "month",
        "dimensions": ["store_format", "region"],
        "unit": "%",
        "owner": "Store Operations",
        "certification": "reviewed",
        "lineage": ["paid_revenue", "SALES_TARGETS.REVENUE_TARGET"],
        "preview": {
            "currentValue": "93.4%",
            "trend": "+3.1 pts vs prior period",
            "breakdown": [
                {"label": "Flagship", "value": "101.2%", "delta": "+5.3 pts"},
                {"label": "Mall", "value": "88.9%", "delta": "+1.4 pts"},
                {"label": "Outlet", "value": "82.0%", "delta": "-2.2 pts"},
            ],
            "explanation": "Aligns monthly paid revenue to SALES_TARGETS by store and target month.",
            "sql": "SELECT store_id, SUM(paid_revenue) / SUM(revenue_target) AS store_attainment FROM modeled_store_month GROUP BY 1",
            "validation": "Validated for monthly grain; daily grain disabled.",
        },
    },
]


DIMENSIONS = [
    {"id": "order_month", "name": "Order Month", "entityId": "orders", "field": "paid_at", "description": "Month bucket from paid timestamp."},
    {"id": "region", "name": "Region", "entityId": "stores", "field": "region", "description": "Store operating region."},
    {"id": "channel", "name": "Channel", "entityId": "orders", "field": "channel_id", "description": "Order acquisition channel."},
    {"id": "store", "name": "Store", "entityId": "stores", "field": "store_id", "description": "Store identifier for operational rollups."},
    {"id": "category", "name": "Product Category", "entityId": "products", "field": "category", "description": "Merchandising product category."},
    {"id": "customer_tier", "name": "Customer Tier", "entityId": "customers", "field": "customer_tier", "description": "Commercial customer tier."},
    {"id": "store_format", "name": "Store Format", "entityId": "stores", "field": "store_format", "description": "Store format classification."},
    {"id": "reason_code", "name": "Refund Reason", "entityId": "refunds", "field": "reason_code", "description": "Refund reason code."},
]


CALCULATED_FIELDS = [
    {
        "id": "paid_order_flag",
        "name": "Paid Order Flag",
        "entityId": "orders",
        "expression": "CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END",
        "description": "Reusable paid-order predicate.",
    },
    {
        "id": "net_revenue_band",
        "name": "Net Revenue Band",
        "entityId": "orders",
        "expression": 'CASE WHEN net_amount >= 500 THEN "High" WHEN net_amount >= 100 THEN "Mid" ELSE "Low" END',
        "description": "Order size grouping.",
    },
]


SUGGESTIONS = [
    {
        "id": "sug-entity-orders",
        "type": "entity",
        "title": "Create Orders as the anchor Entity",
        "recommendation": "Map ORDERS to an Orders entity with ORDER_ID as the primary key and PAID_AT as the preferred revenue time field.",
        "confidence": 0.94,
        "evidence": [
            {"label": "Primary key", "detail": "ORDER_ID is 100% distinct with 0% nulls."},
            {"label": "Profile", "detail": "ORDER_STATUS contains PAID and REFUNDED states used by revenue metrics."},
        ],
        "validation": "Compiles and passes row count sanity checks.",
        "status": "pending",
    },
    {
        "id": "sug-rel-orders-customers",
        "type": "relationship",
        "title": "Confirm Orders to Customers relationship",
        "recommendation": "Join ORDERS.CUSTOMER_ID to CUSTOMERS.CUSTOMER_ID as many-to-one.",
        "confidence": 0.91,
        "evidence": [
            {"label": "FK evidence", "detail": "99.6% of sampled order customer IDs resolve to CUSTOMERS."},
            {"label": "Cardinality", "detail": "CUSTOMERS.CUSTOMER_ID is unique in profile."},
        ],
        "validation": "Fanout risk low, orphan rate 0.4%.",
        "status": "pending",
    },
    {
        "id": "sug-metric-paid-revenue",
        "type": "metric",
        "title": "Define Paid Revenue metric",
        "recommendation": "SUM(ORDERS.NET_AMOUNT) filtered to ORDER_STATUS = PAID, using PAID_AT as the time field.",
        "confidence": 0.89,
        "evidence": [
            {"label": "Column role", "detail": "NET_AMOUNT detected as money and PAID_AT detected as payment timestamp."},
            {"label": "Business rule", "detail": "Refunds are accounted separately in REFUNDS."},
        ],
        "validation": "SQL compiles and returns a stable 90 day trend.",
        "status": "pending",
    },
    {
        "id": "sug-policy-pii",
        "type": "policy",
        "title": "Mask customer contact fields",
        "recommendation": "Mark CUSTOMERS.EMAIL and CUSTOMERS.PHONE as PII and keep them unavailable to semantic MCP tools.",
        "confidence": 0.98,
        "evidence": [
            {"label": "Pattern", "detail": "EMAIL and PHONE match high-confidence PII detectors."},
            {"label": "Usage", "detail": "No current metric needs raw contact fields."},
        ],
        "validation": "Governance warning will clear when the policy is accepted.",
        "status": "pending",
    },
]


ENTITIES = [
    {
        "id": "orders",
        "name": "orders",
        "businessName": "Orders",
        "table": "ORDERS",
        "description": "Order header at one row per submitted order.",
        "primaryKey": "ORDER_ID",
        "type": "fact",
        "fields": [
            {"name": "order_id", "sourceField": "ORDER_ID", "type": "number", "role": "id"},
            {"name": "order_status", "sourceField": "ORDER_STATUS", "type": "string", "role": "status"},
            {"name": "paid_at", "sourceField": "PAID_AT", "type": "timestamp", "role": "time"},
            {"name": "net_amount", "sourceField": "NET_AMOUNT", "type": "number", "role": "amount"},
        ],
    },
    {
        "id": "order_items",
        "name": "order_items",
        "businessName": "Order Items",
        "table": "ORDER_ITEMS",
        "description": "Line item grain for product-level analysis.",
        "primaryKey": "ORDER_ITEM_ID",
        "type": "bridge",
        "fields": [
            {"name": "order_item_id", "sourceField": "ORDER_ITEM_ID", "type": "number", "role": "id"},
            {"name": "quantity", "sourceField": "QUANTITY", "type": "number", "role": "measure"},
            {"name": "item_revenue", "sourceField": "ITEM_REVENUE", "type": "number", "role": "amount"},
        ],
    },
    {
        "id": "customers",
        "name": "customers",
        "businessName": "Customers",
        "table": "CUSTOMERS",
        "description": "Customer dimension with masked PII fields.",
        "primaryKey": "CUSTOMER_ID",
        "type": "dimension",
        "fields": [
            {"name": "customer_id", "sourceField": "CUSTOMER_ID", "type": "number", "role": "id"},
            {"name": "customer_tier", "sourceField": "CUSTOMER_TIER", "type": "string", "role": "attribute"},
        ],
    },
    {
        "id": "products",
        "name": "products",
        "businessName": "Products",
        "table": "PRODUCTS",
        "description": "Product catalog and category hierarchy.",
        "primaryKey": "PRODUCT_ID",
        "type": "dimension",
        "fields": [
            {"name": "product_id", "sourceField": "PRODUCT_ID", "type": "number", "role": "id"},
            {"name": "category", "sourceField": "CATEGORY", "type": "string", "role": "attribute"},
            {"name": "brand", "sourceField": "BRAND", "type": "string", "role": "attribute"},
        ],
    },
    {
        "id": "stores",
        "name": "stores",
        "businessName": "Stores",
        "table": "STORES",
        "description": "Store geography and format.",
        "primaryKey": "STORE_ID",
        "type": "dimension",
        "fields": [
            {"name": "store_id", "sourceField": "STORE_ID", "type": "number", "role": "id"},
            {"name": "region", "sourceField": "REGION", "type": "string", "role": "attribute"},
        ],
    },
    {
        "id": "channels",
        "name": "channels",
        "businessName": "Channels",
        "table": "CHANNELS",
        "description": "Sales and acquisition channels used for order attribution.",
        "primaryKey": "CHANNEL_ID",
        "type": "dimension",
        "fields": [
            {"name": "channel_id", "sourceField": "CHANNEL_ID", "type": "number", "role": "id"},
            {"name": "channel_name", "sourceField": "CHANNEL_NAME", "type": "string", "role": "attribute"},
        ],
    },
    {
        "id": "refunds",
        "name": "refunds",
        "businessName": "Refunds",
        "table": "REFUNDS",
        "description": "Refund events that require order-level aggregation before joining to revenue metrics.",
        "primaryKey": "REFUND_ID",
        "type": "log",
        "fields": [
            {"name": "refund_id", "sourceField": "REFUND_ID", "type": "number", "role": "id"},
            {"name": "refund_amount", "sourceField": "REFUND_AMOUNT", "type": "number", "role": "amount"},
            {"name": "refunded_at", "sourceField": "REFUNDED_AT", "type": "timestamp", "role": "time"},
            {"name": "reason_code", "sourceField": "REASON_CODE", "type": "string", "role": "status"},
        ],
    },
]


class SemanticModelService:
    @staticmethod
    async def ensure_seed(session: AsyncSession, tenant_id: UUID, user_id: UUID | None) -> None:
        existing = await session.execute(
            select(SemanticModel.id).where(SemanticModel.tenant_id == tenant_id, SemanticModel.slug == "sales-growth")
        )
        if existing.scalar_one_or_none():
            return

        async with _seed_lock(tenant_id):
            existing = await session.execute(
                select(SemanticModel.id).where(SemanticModel.tenant_id == tenant_id, SemanticModel.slug == "sales-growth")
            )
            if existing.scalar_one_or_none():
                return
            try:
                await SemanticModelService.create_sales_model(session, tenant_id, user_id, status="Draft")
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.execute(
                    select(SemanticModel.id).where(SemanticModel.tenant_id == tenant_id, SemanticModel.slug == "sales-growth")
                )
                if existing.scalar_one_or_none():
                    return
                raise

    @staticmethod
    async def list_models(session: AsyncSession, tenant_id: UUID, user_id: UUID | None) -> list[dict[str, Any]]:
        await SemanticModelService.ensure_seed(session, tenant_id, user_id)
        result = await session.execute(select(SemanticModel).where(SemanticModel.tenant_id == tenant_id).order_by(SemanticModel.updated_at.desc()))
        return [SemanticModelService.model_to_summary(model) for model in result.scalars().all()]

    @staticmethod
    async def get_model(session: AsyncSession, tenant_id: UUID, model_id: str, user_id: UUID | None = None) -> dict[str, Any] | None:
        await SemanticModelService.ensure_seed(session, tenant_id, user_id)
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        return SemanticModelService.model_to_payload(model) if model else None

    @staticmethod
    async def get_profiles(session: AsyncSession, tenant_id: UUID, user_id: UUID | None) -> list[dict[str, Any]]:
        await SemanticModelService.ensure_seed(session, tenant_id, user_id)
        return [
            deepcopy(DEFAULT_PROFILE),
            {**deepcopy(DEFAULT_PROFILE), "id": "postgres-commerce", "name": "Postgres commerce", "kind": "postgres", "schema": "public", "status": "partial", "profileCoverage": 62},
            {**deepcopy(DEFAULT_PROFILE), "id": "mysql-retail", "name": "MySQL retail mart", "kind": "mysql", "schema": "retail", "status": "stale", "profileCoverage": 48},
        ]

    @staticmethod
    async def create_generation_job(
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        request: dict[str, Any],
    ) -> SemanticModelGenerationJob:
        steps = [{**step, "status": "pending"} for step in GENERATION_STEPS]
        steps[0]["status"] = "running"
        job = SemanticModelGenerationJob(
            tenant_id=tenant_id,
            created_by=user_id,
            datasource_id=request.get("datasource_id") or "oracle-sales",
            status="running",
            phase="profile",
            progress=12,
            steps_json=_json_dump(steps),
            request_json=_json_dump(request),
        )
        session.add(job)
        await SemanticModelService._audit(session, tenant_id, None, user_id, "generation_job_created", request)
        await session.commit()
        await session.refresh(job)
        return job

    @staticmethod
    async def advance_generation_job(
        session: AsyncSession,
        tenant_id: UUID,
        job_id: str,
        user_id: UUID | None,
    ) -> SemanticModelGenerationJob | None:
        job = await session.get(SemanticModelGenerationJob, UUID(job_id))
        if not job or job.tenant_id != tenant_id:
            return None
        steps = _json_load(job.steps_json, [])
        running_index = next((idx for idx, step in enumerate(steps) if step.get("status") == "running"), -1)
        next_index = running_index + 1

        if next_index < len(steps):
            for idx, step in enumerate(steps):
                step["status"] = "done" if idx < next_index else "running" if idx == next_index else "pending"
            job.steps_json = _json_dump(steps)
            job.progress = min(96, round(((next_index + 1) / len(steps)) * 100))
            job.phase = "profile" if next_index < 2 else "semantic" if next_index < 6 else "validation"
        else:
            for step in steps:
                step["status"] = "done"
            model = await SemanticModelService._load_model(session, tenant_id, "sales-growth")
            if not model:
                model = await SemanticModelService.create_sales_model(session, tenant_id, user_id, status="Draft")
            model.draft_revision = "draft-8"
            model.validation_log_json = _json_dump(["Generation job completed and semantic draft refreshed.", *_json_load(model.validation_log_json, [])])
            SemanticModelService._recalculate_readiness(model)
            job.steps_json = _json_dump(steps)
            job.status = "completed"
            job.phase = "completed"
            job.progress = 100
            job.result_model_id = model.id
            await SemanticModelService._audit(session, tenant_id, model.id, user_id, "generation_job_completed", {"job_id": job_id})
        await session.commit()
        await session.refresh(job)
        return job

    @staticmethod
    async def update_relationship(
        session: AsyncSession,
        tenant_id: UUID,
        model_id: str,
        relationship_id: str,
        patch: dict[str, Any],
        user_id: UUID | None,
    ) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        relationship = next((rel for rel in model.relationships if rel.slug == relationship_id), None)
        if not relationship:
            return None
        mapping = {
            "cardinality": "cardinality",
            "uniqueRate": "unique_rate",
            "orphanRate": "orphan_rate",
            "fanoutRisk": "fanout_risk",
            "validationStatus": "validation_status",
            "status": "status",
            "validationMessage": "validation_message",
        }
        for key, attr in mapping.items():
            if key in patch and patch[key] is not None:
                setattr(relationship, attr, patch[key])
        model.validation_log_json = _json_dump([f"Relationship {relationship_id} updated.", *_json_load(model.validation_log_json, [])])
        SemanticModelService._recalculate_readiness(model)
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "relationship_updated", {"relationship": relationship_id, "patch": patch})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def fix_fanout_relationship(session: AsyncSession, tenant_id: UUID, model_id: str, relationship_id: str, user_id: UUID | None) -> dict[str, Any] | None:
        return await SemanticModelService.update_relationship(
            session,
            tenant_id,
            model_id,
            relationship_id,
            {
                "cardinality": "one-to-many",
                "uniqueRate": 99.1,
                "orphanRate": 0.9,
                "fanoutRisk": "medium",
                "validationStatus": "valid",
                "status": "confirmed",
                "validationMessage": "Fixed by modeling refunds as a pre-aggregated order-level subquery.",
            },
            user_id,
        )

    @staticmethod
    async def reject_relationship(session: AsyncSession, tenant_id: UUID, model_id: str, relationship_id: str, user_id: UUID | None) -> dict[str, Any] | None:
        return await SemanticModelService.update_relationship(
            session,
            tenant_id,
            model_id,
            relationship_id,
            {"status": "rejected", "validationStatus": "warning", "validationMessage": "Rejected for this model version; refund metrics must use explicit aggregate SQL."},
            user_id,
        )

    @staticmethod
    async def update_metric(
        session: AsyncSession,
        tenant_id: UUID,
        model_id: str,
        metric_id: str,
        patch: dict[str, Any],
        user_id: UUID | None,
    ) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        metric = next((item for item in model.metrics if item.slug == metric_id), None)
        if not metric:
            return None
        mapping = {
            "businessName": "business_name",
            "definition": "definition",
            "kind": "kind",
            "formula": "formula",
            "filter": "filter_expr",
            "timeField": "time_field",
            "defaultGrain": "default_grain",
            "unit": "unit",
            "owner": "owner",
            "certification": "certification",
        }
        before = SemanticModelService.metric_to_payload(metric)
        for key, attr in mapping.items():
            if key in patch and patch[key] is not None:
                setattr(metric, attr, patch[key])
        if "dimensions" in patch and patch["dimensions"] is not None:
            metric.dimensions_json = _json_dump(patch["dimensions"])
        SemanticModelService._refresh_metric_preview(metric, before, patch)
        model.validation_log_json = _json_dump([f"Metric {metric_id} preview refreshed.", *_json_load(model.validation_log_json, [])])
        SemanticModelService._recalculate_readiness(model)
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "metric_updated", {"metric": metric_id, "patch": patch})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def update_explore(session: AsyncSession, tenant_id: UUID, model_id: str, patch: dict[str, Any], user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        explore = _json_load(model.explore_json, {})
        explore.update({key: value for key, value in patch.items() if value is not None})
        model.explore_json = _json_dump(explore)
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "explore_updated", patch)
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def save_explore_artifact(session: AsyncSession, tenant_id: UUID, model_id: str, kind: str, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        explore = _json_load(model.explore_json, {})
        consumers = _json_load(model.consumers_json, {})
        if kind == "query":
            explore["savedQueryCount"] = int(explore.get("savedQueryCount", 0)) + 1
            consumers["savedQueries"] = int(consumers.get("savedQueries", 0)) + 1
        elif kind == "dashboard":
            explore["dashboardAdds"] = int(explore.get("dashboardAdds", 0)) + 1
            consumers["dashboards"] = int(consumers.get("dashboards", 0)) + 1
        elif kind == "skill":
            explore["skillDrafts"] = int(explore.get("skillDrafts", 0)) + 1
            consumers["skills"] = int(consumers.get("skills", 0)) + 1
        elif kind == "example":
            explore["confirmedExamples"] = int(explore.get("confirmedExamples", 0)) + 1
        else:
            raise ValueError("Unsupported artifact kind")
        model.explore_json = _json_dump(explore)
        model.consumers_json = _json_dump(consumers)
        session.add(
            SemanticModelConsumer(
                model_id=model.id,
                version_label=model.published_version,
                consumer_type=kind,
                reference_name=f"{kind}-{explore.get('metricId', 'metric')}-{datetime.utcnow().strftime('%H%M%S')}",
                details_json=_json_dump({"explore": explore}),
                created_by=user_id,
            )
        )
        model.validation_log_json = _json_dump([f"Saved Explore result as {kind}.", *_json_load(model.validation_log_json, [])])
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "explore_artifact_saved", {"kind": kind})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def suggestion_action(session: AsyncSession, tenant_id: UUID, model_id: str, suggestion_id: str, action: str, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        suggestion = next((item for item in model.suggestions if item.slug == suggestion_id), None)
        if not suggestion:
            return None
        if action not in {"accepted", "edited", "rejected"}:
            raise ValueError("Unsupported suggestion action")
        suggestion.status = action
        if action == "edited":
            suggestion.edited_note = "Business wording adjusted before accepting."
        model.validation_log_json = _json_dump([f"Suggestion {suggestion_id} {action}.", *_json_load(model.validation_log_json, [])])
        SemanticModelService._recalculate_readiness(model)
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "suggestion_updated", {"suggestion": suggestion_id, "action": action})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def validate_model(session: AsyncSession, tenant_id: UUID, model_id: str, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        SemanticModelService._recalculate_readiness(model)
        session.add(
            SemanticModelValidationResult(
                model_id=model.id,
                result_type="full_model",
                status=model.readiness_level,
                message="Validation run completed across relationships, metrics, PII, and examples.",
                details_json=_json_dump(SemanticModelService._readiness_detail(model)),
            )
        )
        model.validation_log_json = _json_dump(["Validation run completed across relationships, metrics, PII, and examples.", *_json_load(model.validation_log_json, [])])
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "model_validated", {"readiness": model.readiness})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def update_review(session: AsyncSession, tenant_id: UUID, model_id: str, patch: dict[str, Any], user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        review = _json_load(model.review_json, {})
        review.update(patch)
        model.review_json = _json_dump(review)
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "review_updated", patch)
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def publish_model(session: AsyncSession, tenant_id: UUID, model_id: str, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        current_number = 0
        if model.published_version.startswith("v") and model.published_version[1:].isdigit():
            current_number = int(model.published_version[1:])
        next_label = f"v{max(3, current_number + 1)}"
        review = _json_load(model.review_json, {})
        review.update({"reviewed": True, "opened": False, "publishedAt": _now_label()})
        model.review_json = _json_dump(review)
        model.status = "Published"
        model.published_version = next_label
        model.draft_revision = "clean"
        model.drift_alerts = 0
        mcp = _json_load(model.mcp_json, {})
        mcp["exposedVersion"] = next_label
        model.mcp_json = _json_dump(mcp)
        SemanticModelService._recalculate_readiness(model)
        snapshot = SemanticModelService.model_to_payload(model)
        version = SemanticModelVersion(
            model_id=model.id,
            version_label=next_label,
            snapshot_json=_json_dump(snapshot),
            publish_notes=review.get("publishNotes", ""),
            created_by=user_id,
        )
        session.add(version)
        await session.flush()
        session.add(
            SemanticModelPublication(
                model_id=model.id,
                version_id=version.id,
                version_label=next_label,
                created_by=user_id,
            )
        )
        model.validation_log_json = _json_dump([f"Published Semantic Model {next_label}.", *_json_load(model.validation_log_json, [])])
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "model_published", {"version": next_label})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def set_raw_sql_fallback(session: AsyncSession, tenant_id: UUID, model_id: str, enabled: bool, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        mcp = _json_load(model.mcp_json, {})
        mcp["rawSqlFallback"] = enabled
        model.mcp_json = _json_dump(mcp)
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "mcp_policy_updated", {"rawSqlFallback": enabled})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def run_mcp_query(session: AsyncSession, tenant_id: UUID, model_id: str, request: dict[str, Any], user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService._load_model(session, tenant_id, model_id)
        if not model:
            return None
        explore = _json_load(model.explore_json, {})
        metric_id = request.get("metric") or explore.get("metricId") or "paid_revenue"
        metric = next((item for item in model.metrics if item.slug == metric_id), model.metrics[0] if model.metrics else None)
        if metric is None:
            return None
        mcp = _json_load(model.mcp_json, {})
        preview = _json_load(metric.preview_json, {})
        last_result = {
            "resolvedMetric": metric.business_name,
            "modelVersion": mcp.get("exposedVersion", model.published_version),
            "result": preview.get("currentValue", ""),
            "freshness": "Profile refreshed 2h ago; semantic version immutable.",
            "lineage": _json_load(metric.lineage_json, []),
            "policyDecision": "Allowed semantic tool; raw SQL fallback remains separately audited."
            if mcp.get("rawSqlFallback")
            else "Allowed semantic tool; raw SQL fallback denied by default.",
        }
        mcp["lastResult"] = last_result
        model.mcp_json = _json_dump(mcp)
        model.validation_log_json = _json_dump([f"MCP query_metric resolved {metric.business_name}.", *_json_load(model.validation_log_json, [])])
        await SemanticModelService._audit(session, tenant_id, model.id, user_id, "mcp_query_metric", {"request": request, "result": last_result})
        await session.commit()
        return SemanticModelService.model_to_payload(model)

    @staticmethod
    async def create_sales_model(session: AsyncSession, tenant_id: UUID, user_id: UUID | None, status: str = "Draft") -> SemanticModel:
        model = SemanticModel(
            tenant_id=tenant_id,
            created_by=user_id,
            slug="sales-growth",
            name="Sales Growth Model",
            domain="Sales / Orders",
            owner="Revenue Analytics",
            datasource_id="oracle-sales",
            datasource_name="Oracle SALES",
            datasource_kind="oracle",
            description="Business semantic model for orders, revenue, refunds, store performance, and customer segmentation.",
            status=status,
            draft_revision="draft-7",
            published_version="v2",
            readiness=73,
            readiness_level="warning",
            drift_alerts=2,
            consumers_json=_json_dump({"agents": 3, "mcp": 2, "skills": 1, "dashboards": 4, "savedQueries": 8}),
            explore_json=_json_dump(
                {
                    "metricId": "paid_revenue",
                    "dimensionId": "region",
                    "grain": "month",
                    "timeRange": "90d",
                    "filter": "order_status = 'PAID'",
                    "viewMode": "trend",
                    "savedQueryCount": 8,
                    "dashboardAdds": 4,
                    "skillDrafts": 1,
                    "confirmedExamples": 12,
                }
            ),
            review_json=_json_dump(
                {
                    "opened": False,
                    "reviewed": False,
                    "publishNotes": "Clarify refund fanout handling, certify Paid Revenue, and expose v3 semantic tools for revenue agents.",
                }
            ),
            mcp_json=_json_dump(
                {
                    "exposedVersion": "v2",
                    "consumerIdentity": "revenue-agent@local",
                    "rawSqlFallback": False,
                    "allowedMetrics": ["paid_revenue", "order_count", "avg_order_value", "store_attainment"],
                    "allowedDimensions": ["order_month", "region", "channel", "category", "store_format"],
                }
            ),
            validation_log_json=_json_dump(["Draft loaded from v2 semantic contract.", "Oracle SALES profile refreshed at 2026-08-14 09:30."]),
        )
        session.add(model)
        await session.flush()
        for idx, item in enumerate(ENTITIES):
            entity = SemanticModelEntity(
                model_id=model.id,
                slug=item["id"],
                name=item["name"],
                business_name=item["businessName"],
                table_name=item["table"],
                description=item["description"],
                primary_key=item["primaryKey"],
                entity_type=item.get("type", "dimension"),
                validation_status="valid",
                profile_json=_json_dump(next((table for table in SALES_TABLES if table["name"] == item["table"]), {})),
                lineage_json=_json_dump([item["table"]]),
                permission_json=_json_dump({"mcp": "semantic_only"}),
                sort_order=idx,
            )
            session.add(entity)
            await session.flush()
            for field_idx, field in enumerate(item["fields"]):
                session.add(
                    SemanticModelField(
                        entity_id=entity.id,
                        name=field["name"],
                        source_field=field["sourceField"],
                        data_type=field["type"],
                        role=field["role"],
                        nullable=True,
                        profile_json=_json_dump({}),
                        sort_order=field_idx,
                    )
                )
        for idx, rel in enumerate(RELATIONSHIPS):
            session.add(
                SemanticModelRelationship(
                    model_id=model.id,
                    slug=rel["id"],
                    from_entity=rel["fromEntity"],
                    to_entity=rel["toEntity"],
                    label=rel["label"],
                    join_fields_json=_json_dump(rel["joinFields"]),
                    cardinality=rel["cardinality"],
                    fk_evidence=rel["fkEvidence"],
                    unique_rate=rel["uniqueRate"],
                    orphan_rate=rel["orphanRate"],
                    fanout_risk=rel["fanoutRisk"],
                    validation_status=rel["validationStatus"],
                    status=rel["status"],
                    validation_message=rel["validationMessage"],
                    evidence_json=_json_dump([{"label": "Profile", "detail": rel["fkEvidence"]}]),
                    sort_order=idx,
                )
            )
        for idx, metric in enumerate(METRICS):
            session.add(
                SemanticModelMetric(
                    model_id=model.id,
                    slug=metric["id"],
                    name=metric["name"],
                    business_name=metric["businessName"],
                    definition=metric["definition"],
                    kind=metric["kind"],
                    formula=metric["formula"],
                    filter_expr=metric["filter"],
                    time_field=metric["timeField"],
                    default_grain=metric["defaultGrain"],
                    dimensions_json=_json_dump(metric["dimensions"]),
                    unit=metric["unit"],
                    owner=metric["owner"],
                    certification=metric["certification"],
                    lineage_json=_json_dump(metric["lineage"]),
                    preview_json=_json_dump(metric["preview"]),
                    compiled_sql=metric["preview"]["sql"],
                    validation_status="valid" if metric["id"] != "refund_rate" else "blocked",
                    sort_order=idx,
                )
            )
        for idx, dimension in enumerate(DIMENSIONS):
            session.add(
                SemanticModelDimension(
                    model_id=model.id,
                    slug=dimension["id"],
                    name=dimension["name"],
                    entity_slug=dimension["entityId"],
                    field=dimension["field"],
                    description=dimension["description"],
                    sort_order=idx,
                )
            )
        for idx, calculated in enumerate(CALCULATED_FIELDS):
            session.add(
                SemanticModelCalculatedField(
                    model_id=model.id,
                    slug=calculated["id"],
                    name=calculated["name"],
                    entity_slug=calculated["entityId"],
                    expression=calculated["expression"],
                    description=calculated["description"],
                    sort_order=idx,
                )
            )
        for idx, suggestion in enumerate(SUGGESTIONS):
            session.add(
                SemanticModelSuggestion(
                    model_id=model.id,
                    slug=suggestion["id"],
                    suggestion_type=suggestion["type"],
                    title=suggestion["title"],
                    recommendation=suggestion["recommendation"],
                    confidence=suggestion["confidence"],
                    evidence_json=_json_dump(suggestion["evidence"]),
                    validation=suggestion["validation"],
                    status=suggestion["status"],
                    sort_order=idx,
                )
            )
        return model

    @staticmethod
    async def _load_model(session: AsyncSession, tenant_id: UUID, model_id: str) -> SemanticModel | None:
        stmt = (
            select(SemanticModel)
            .where(SemanticModel.tenant_id == tenant_id, SemanticModel.slug == model_id)
            .options(
                selectinload(SemanticModel.entities).selectinload(SemanticModelEntity.fields),
                selectinload(SemanticModel.relationships),
                selectinload(SemanticModel.metrics),
                selectinload(SemanticModel.dimensions),
                selectinload(SemanticModel.calculated_fields),
                selectinload(SemanticModel.suggestions),
                selectinload(SemanticModel.validation_results),
                selectinload(SemanticModel.versions),
            )
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def model_to_summary(model: SemanticModel) -> dict[str, Any]:
        updated_at = model.__dict__.get("updated_at") or model.__dict__.get("created_at")
        return {
            "id": model.slug,
            "name": model.name,
            "domain": model.domain,
            "owner": model.owner,
            "datasource": model.datasource_name,
            "status": model.status,
            "draftRevision": model.draft_revision,
            "publishedVersion": model.published_version,
            "readiness": model.readiness,
            "readinessLevel": model.readiness_level,
            "driftAlerts": model.drift_alerts,
            "consumers": _json_load(model.consumers_json, {}),
            "updatedAt": updated_at.strftime("%Y-%m-%d %H:%M") if updated_at else _now_label(),
        }

    @staticmethod
    def model_to_payload(model: SemanticModel) -> dict[str, Any]:
        summary = SemanticModelService.model_to_summary(model)
        return {
            **summary,
            "description": model.description,
            "datasourceId": model.datasource_id,
            "entities": [SemanticModelService.entity_to_payload(entity) for entity in model.entities],
            "relationships": [SemanticModelService.relationship_to_payload(rel) for rel in model.relationships],
            "metrics": [SemanticModelService.metric_to_payload(metric) for metric in model.metrics],
            "dimensions": [
                {
                    "id": item.slug,
                    "name": item.name,
                    "entityId": item.entity_slug,
                    "field": item.field,
                    "description": item.description,
                }
                for item in model.dimensions
            ],
            "calculatedFields": [
                {
                    "id": item.slug,
                    "name": item.name,
                    "entityId": item.entity_slug,
                    "expression": item.expression,
                    "description": item.description,
                }
                for item in model.calculated_fields
            ],
            "suggestions": [
                {
                    "id": item.slug,
                    "type": item.suggestion_type,
                    "title": item.title,
                    "recommendation": item.recommendation,
                    "confidence": item.confidence,
                    "evidence": _json_load(item.evidence_json, []),
                    "validation": item.validation,
                    "status": item.status,
                    "editedNote": item.edited_note,
                }
                for item in model.suggestions
            ],
            "readinessDetail": SemanticModelService._readiness_detail(model),
            "explore": _json_load(model.explore_json, {}),
            "review": _json_load(model.review_json, {}),
            "mcp": _json_load(model.mcp_json, {}),
            "validationLog": _json_load(model.validation_log_json, []),
        }

    @staticmethod
    def entity_to_payload(entity: SemanticModelEntity) -> dict[str, Any]:
        return {
            "id": entity.slug,
            "name": entity.name,
            "businessName": entity.business_name,
            "table": entity.table_name,
            "description": entity.description,
            "primaryKey": entity.primary_key,
            "fields": [
                {
                    "name": field.name,
                    "sourceField": field.source_field,
                    "type": field.data_type,
                    "role": field.role,
                }
                for field in entity.fields
            ],
        }

    @staticmethod
    def relationship_to_payload(relationship: SemanticModelRelationship) -> dict[str, Any]:
        return {
            "id": relationship.slug,
            "fromEntity": relationship.from_entity,
            "toEntity": relationship.to_entity,
            "label": relationship.label,
            "joinFields": _json_load(relationship.join_fields_json, []),
            "cardinality": relationship.cardinality,
            "fkEvidence": relationship.fk_evidence,
            "uniqueRate": relationship.unique_rate,
            "orphanRate": relationship.orphan_rate,
            "fanoutRisk": relationship.fanout_risk,
            "validationStatus": relationship.validation_status,
            "status": relationship.status,
            "validationMessage": relationship.validation_message,
        }

    @staticmethod
    def metric_to_payload(metric: SemanticModelMetric) -> dict[str, Any]:
        preview = _json_load(metric.preview_json, {})
        if metric.compiled_sql and not preview.get("sql"):
            preview["sql"] = metric.compiled_sql
        return {
            "id": metric.slug,
            "name": metric.name,
            "businessName": metric.business_name,
            "definition": metric.definition,
            "kind": metric.kind,
            "formula": metric.formula,
            "filter": metric.filter_expr,
            "timeField": metric.time_field,
            "defaultGrain": metric.default_grain,
            "dimensions": _json_load(metric.dimensions_json, []),
            "unit": metric.unit,
            "owner": metric.owner,
            "certification": metric.certification,
            "lineage": _json_load(metric.lineage_json, []),
            "preview": preview,
        }

    @staticmethod
    def job_to_payload(job: SemanticModelGenerationJob) -> dict[str, Any]:
        return {
            "id": str(job.id),
            "datasource_id": job.datasource_id,
            "status": job.status,
            "phase": job.phase,
            "progress": job.progress,
            "steps": _json_load(job.steps_json, []),
            "result_model_id": "sales-growth" if job.result_model_id else None,
            "error": job.error,
        }

    @staticmethod
    def _readiness_detail(model: SemanticModel) -> dict[str, Any]:
        fanout_blocked = any(rel.validation_status == "blocked" and rel.status != "rejected" for rel in model.relationships)
        pii_accepted = any(item.slug == "sug-policy-pii" and item.status != "pending" for item in model.suggestions)
        certified_core = any(item.slug == "paid_revenue" and item.certification == "certified" for item in model.metrics)
        accepted = len([item for item in model.suggestions if item.status in {"accepted", "edited"}])
        structural = min(96, 84 + accepted * 2)
        semantic = min(94, 74 + accepted * 3)
        query = 66 if fanout_blocked else 88
        governance = min(92, 62 + (16 if pii_accepted else 0) + (10 if certified_core else 0))
        evidence = min(95, 79 + accepted * 2)
        blockers = ["Orders -> Refunds fanout candidate is unresolved."] if fanout_blocked else []
        warnings = []
        if not pii_accepted:
            warnings.append("Customer contact fields need a confirmed PII policy.")
        if not certified_core:
            warnings.append("Paid Revenue should be certified before broad MCP exposure.")
        if any(item.slug == "refund_rate" and item.certification == "draft" for item in model.metrics):
            warnings.append("Refund Rate is still draft certified.")
        score = round(structural * 0.2 + semantic * 0.25 + query * 0.25 + governance * 0.15 + evidence * 0.15)
        level = "blocked" if blockers else "ready" if score >= 85 else "warning" if score >= 65 else "blocked"
        reliable = [
            "What was paid revenue by month and region?",
            "Which product categories drove order growth last quarter?",
            "How are flagship stores tracking against monthly targets?",
        ]
        if not fanout_blocked:
            reliable.append("What is refund rate by region and product category?")
        unreliable = ["Which individual customers should be contacted?"]
        if fanout_blocked:
            unreliable.insert(0, "What is refund rate by product before refund fanout is fixed?")
        return {
            "score": score,
            "level": level,
            "components": [
                {"id": "structural", "name": "Structural completeness", "score": structural, "status": "ready" if structural >= 85 else "warning"},
                {"id": "semantic", "name": "Semantic completeness", "score": semantic, "status": "ready" if semantic >= 85 else "warning"},
                {"id": "query", "name": "Query correctness", "score": query, "status": "blocked" if fanout_blocked else "ready"},
                {"id": "governance", "name": "Governance", "score": governance, "status": "ready" if governance >= 85 else "warning"},
                {"id": "evidence", "name": "Evidence coverage", "score": evidence, "status": "ready" if evidence >= 85 else "warning"},
            ],
            "reliableQuestions": reliable,
            "unreliableQuestions": unreliable,
            "blockers": blockers,
            "warnings": warnings,
        }

    @staticmethod
    def _recalculate_readiness(model: SemanticModel) -> None:
        readiness = SemanticModelService._readiness_detail(model)
        model.readiness = readiness["score"]
        model.readiness_level = readiness["level"]

    @staticmethod
    def _refresh_metric_preview(metric: SemanticModelMetric, before: dict[str, Any], patch: dict[str, Any]) -> None:
        preview = _json_load(metric.preview_json, {})
        signature = f"{metric.formula}|{metric.filter_expr}|{metric.time_field}|{metric.default_grain}"
        deterministic_delta = len(signature) % 7
        if metric.slug == "paid_revenue":
            current_value = f"${(8.48 + deterministic_delta * 0.03):.2f}M"
        elif metric.slug == "avg_order_value":
            current_value = f"${(73.24 + deterministic_delta * 0.41):.2f}"
        elif metric.unit == "%":
            current_value = f"{(4.8 + deterministic_delta * 0.2):.1f}%"
        else:
            current_value = preview.get("currentValue", before.get("preview", {}).get("currentValue", ""))
        preview.update(
            {
                "currentValue": current_value,
                "trend": f"+{(10.8 + deterministic_delta * 0.7):.1f}% vs prior period",
                "validation": "Certified by owner and ready for semantic MCP exposure. Compiled by the Team Version semantic service."
                if patch.get("certification") == "certified"
                else "Compiled successfully; preview refreshed from the Team Version semantic service.",
                "sql": f"SELECT {metric.formula} AS {metric.name}\nFROM semantic_model.sales_growth\nWHERE {metric.filter_expr}\n-- time: {metric.time_field}; grain: {metric.default_grain}",
            }
        )
        metric.preview_json = _json_dump(preview)
        metric.compiled_sql = preview["sql"]

    @staticmethod
    async def _audit(
        session: AsyncSession,
        tenant_id: UUID,
        model_id: UUID | None,
        user_id: UUID | None,
        action: str,
        details: dict[str, Any],
    ) -> None:
        session.add(
            SemanticModelAuditEvent(
                tenant_id=tenant_id,
                model_id=model_id,
                user_id=user_id,
                action=action,
                details_json=_json_dump(details),
            )
        )
