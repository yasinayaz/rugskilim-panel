import fs from "node:fs/promises";
import path from "node:path";

import {
  SpreadsheetFile,
  Workbook,
} from "file:///Users/yasinayaz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const repoRoot = "/Users/yasinayaz/Projeler/rugskilim-panel";
const envPath = path.join(repoRoot, "streamlit", ".env");
const outputDir = path.join(repoRoot, "outputs", "missing-products-report");
const outputPath = path.join(outputDir, "supabase_urun_eksik_kategori_olcu_raporu.xlsx");

function parseEnv(text) {
  const out = {};
  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const idx = line.indexOf("=");
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    out[key] = value;
  }
  return out;
}

function clean(value) {
  return String(value ?? "").trim();
}

function hasAnyMeasurement(product) {
  const fields = [
    "width_cm",
    "length_cm",
    "size_cm",
    "area_m2",
    "width_ft",
    "length_ft",
    "size_ft",
  ];
  return fields.some((field) => clean(product[field]));
}

function isMissingProduct(product) {
  const missingCategory = !clean(product.category);
  const missingMeasurement = !hasAnyMeasurement(product);
  return missingCategory || missingMeasurement;
}

async function fetchAllRows({ url, key, table, order, select }) {
  const rows = [];
  const pageSize = 1000;
  let offset = 0;
  while (true) {
    const apiUrl = new URL(`${url}/rest/v1/${table}`);
    apiUrl.searchParams.set("select", select);
    if (order) apiUrl.searchParams.set("order", order);
    const response = await fetch(apiUrl, {
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        Accept: "application/json",
        "Range-Unit": "items",
        Range: `${offset}-${offset + pageSize - 1}`,
      },
    });
    if (!response.ok) {
      throw new Error(`${table} okunamadı: ${response.status} ${await response.text()}`);
    }
    const page = await response.json();
    rows.push(...page);
    if (page.length < pageSize) break;
    offset += pageSize;
  }
  return rows;
}

function buildStoreMap(storeRows) {
  const map = new Map();
  for (const row of storeRows) {
    const code = clean(row.product_code);
    const storeId = clean(row.store_id);
    const renk = clean(row.renk).toLowerCase();
    const status = clean(row.status).toLowerCase();
    if (!code || !storeId) continue;
    if (renk !== "green" && status !== "done") continue;
    if (!map.has(code)) map.set(code, new Set());
    map.get(code).add(storeId);
  }
  return map;
}

function normalizeProduct(product, storeMap) {
  const code = clean(product.product_code);
  const stores = Array.from(storeMap.get(code) || []).sort();
  const loadedStores = clean(product.loaded_stores) || stores.join(", ");
  const loadedStoreCount = Number(product.loaded_store_count || stores.length || 0);
  return {
    product_code: code,
    category: clean(product.category),
    size_cm: clean(product.size_cm),
    size_ft: clean(product.size_ft),
    width_cm: clean(product.width_cm),
    length_cm: clean(product.length_cm),
    width_ft: clean(product.width_ft),
    length_ft: clean(product.length_ft),
    area_m2: clean(product.area_m2),
    status: clean(product.status) || "active",
    source_tab: clean(product.source_tab),
    updated_at: clean(product.updated_at),
    loaded_store_count: loadedStoreCount,
    loaded_stores: loadedStores,
    note: clean(product.note),
    missing_category: !clean(product.category) ? "Evet" : "",
    missing_measurement: !hasAnyMeasurement(product) ? "Evet" : "",
  };
}

function worksheetRows(products, includeMissingFlags) {
  const header = [
    "product_code",
    "category",
    "size_cm",
    "size_ft",
    "width_cm",
    "length_cm",
    "width_ft",
    "length_ft",
    "area_m2",
    "loaded_store_count",
    "loaded_stores",
    "status",
    "source_tab",
    "updated_at",
    "note",
  ];
  if (includeMissingFlags) {
    header.splice(1, 0, "missing_category", "missing_measurement");
  }

  const body = products.map((product) => {
    const base = [
      product.product_code,
      product.category,
      product.size_cm,
      product.size_ft,
      product.width_cm,
      product.length_cm,
      product.width_ft,
      product.length_ft,
      product.area_m2,
      product.loaded_store_count,
      product.loaded_stores,
      product.status,
      product.source_tab,
      product.updated_at,
      product.note,
    ];
    if (includeMissingFlags) {
      base.splice(1, 0, product.missing_category, product.missing_measurement);
    }
    return base;
  });

  return [header, ...body];
}

function applyBasicFormatting(sheet, rowCount, colCount) {
  sheet.getRangeByIndexes(0, 0, 1, colCount).format.fill.color = "#1F4E78";
  sheet.getRangeByIndexes(0, 0, 1, colCount).format.font.color = "#FFFFFF";
  sheet.getRangeByIndexes(0, 0, 1, colCount).format.font.bold = true;
  sheet.freezePanes.freezeRows(1);
  if (rowCount > 1) {
    sheet.getRangeByIndexes(1, 0, rowCount - 1, colCount).format.wrapText = false;
  }
}

const env = parseEnv(await fs.readFile(envPath, "utf8"));
const supabaseUrl = clean(env.SUPABASE_URL).replace(/\/$/, "");
const supabaseKey = clean(env.SUPABASE_SERVICE_ROLE_KEY);
const productsTable = clean(env.SUPABASE_PRODUCTS_TABLE) || "products";

if (!supabaseUrl || !supabaseKey) {
  throw new Error("SUPABASE_URL veya SUPABASE_SERVICE_ROLE_KEY eksik.");
}

const [products, storeRows] = await Promise.all([
  fetchAllRows({
    url: supabaseUrl,
    key: supabaseKey,
    table: productsTable,
    order: "product_code.asc",
    select: "*",
  }),
  fetchAllRows({
    url: supabaseUrl,
    key: supabaseKey,
    table: "product_store_status",
    order: "product_code.asc",
    select: "product_code,store_id,status,renk",
  }),
]);

const storeMap = buildStoreMap(storeRows);
const normalized = products
  .map((product) => normalizeProduct(product, storeMap))
  .sort((a, b) => a.product_code.localeCompare(b.product_code, "tr"));

const missingProducts = normalized.filter(isMissingProduct);
const remainingProducts = normalized.filter((product) => !isMissingProduct(product));

const workbook = Workbook.create();

const summarySheet = workbook.worksheets.add("Eksik Bilgili Urunler");
const remainingSheet = workbook.worksheets.add("Kalan Urunler");

const missingRows = worksheetRows(missingProducts, true);
const remainingRows = worksheetRows(remainingProducts, false);

summarySheet.getRange(`A1:${String.fromCharCode(64 + missingRows[0].length)}${missingRows.length}`).values = missingRows;
remainingSheet.getRange(`A1:${String.fromCharCode(64 + remainingRows[0].length)}${remainingRows.length}`).values = remainingRows;

applyBasicFormatting(summarySheet, missingRows.length, missingRows[0].length);
applyBasicFormatting(remainingSheet, remainingRows.length, remainingRows[0].length);

const summaryInspect = await workbook.inspect({
  kind: "table",
  range: `Eksik Bilgili Urunler!A1:${String.fromCharCode(64 + Math.min(missingRows[0].length, 8))}${Math.min(missingRows.length, 10)}`,
  include: "values",
  tableMaxRows: 10,
  tableMaxCols: 8,
});

const remainingInspect = await workbook.inspect({
  kind: "table",
  range: `Kalan Urunler!A1:${String.fromCharCode(64 + Math.min(remainingRows[0].length, 8))}${Math.min(remainingRows.length, 10)}`,
  include: "values",
  tableMaxRows: 10,
  tableMaxCols: 8,
});

await workbook.render({ sheetName: "Eksik Bilgili Urunler", range: `A1:${String.fromCharCode(64 + Math.min(missingRows[0].length, 8))}${Math.min(missingRows.length, 25)}`, scale: 1 });
await workbook.render({ sheetName: "Kalan Urunler", range: `A1:${String.fromCharCode(64 + Math.min(remainingRows[0].length, 8))}${Math.min(remainingRows.length, 25)}`, scale: 1 });

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  totalProducts: normalized.length,
  missingProducts: missingProducts.length,
  remainingProducts: remainingProducts.length,
  summaryInspect: summaryInspect.ndjson,
  remainingInspect: remainingInspect.ndjson,
}, null, 2));
