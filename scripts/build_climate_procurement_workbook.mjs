import fs from "node:fs/promises";
import path from "node:path";

import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const FONT_FAMILY = "Arial";
const COLORS = {
  navy: "#17365D",
  teal: "#0F6B78",
  lightTeal: "#DDEBF7",
  paleBlue: "#EAF2F8",
  paleGreen: "#E2F0D9",
  paleAmber: "#FFF2CC",
  paleRed: "#FCE4D6",
  gray: "#F2F2F2",
  midGray: "#D9E1F2",
  text: "#1F2937",
  white: "#FFFFFF",
};

const NOTICE_COLUMNS = [
  ["record_id", "공고 고유ID"],
  ["bid_notice_no", "입찰공고번호"],
  ["bid_notice_order", "공고차수"],
  ["notice_title", "공고명"],
  ["notice_date", "공고일시"],
  ["notice_year", "공고연도"],
  ["notice_kind", "공고종류"],
  ["rebid_yn", "재공고 여부"],
  ["notice_agency", "공고기관"],
  ["demand_agency", "수요기관"],
  ["bid_method", "입찰방식"],
  ["contract_method", "계약방법"],
  ["award_method", "낙찰방법"],
  ["service_type", "용역구분"],
  ["budget_amount_krw", "배정예산(원)"],
  ["estimated_price_krw", "추정가격(원)"],
  ["vat_amount_krw", "부가세(원)"],
  ["bid_start", "입찰개시일시"],
  ["bid_close", "입찰마감일시"],
  ["opening_date", "개찰일시"],
  ["participant_limit_yn", "참가제한 여부"],
  ["joint_contract_method", "공동계약 방식"],
  ["order_plan_unified_no", "발주계획통합번호"],
  ["pre_spec_registration_no", "사전규격등록번호"],
  ["procurement_request_no", "조달요청번호"],
  ["search_terms", "검색어"],
  ["categories", "기후·ESG 분류"],
  ["relevance_status", "관련성 판정"],
  ["relevance_reason", "판정 근거"],
  ["tracker_tier", "트래커 등급"],
  ["tracker_score", "트래커 점수"],
  ["matched_keywords", "매칭 키워드"],
  ["winner_count", "낙찰결과 수"],
  ["participant_count", "참여기업 수"],
  ["winner_company", "낙찰기업"],
  ["winner_business_no", "낙찰기업 사업자번호"],
  ["award_amount_krw", "낙찰금액(원)"],
  ["award_rate_pct", "낙찰률(%)"],
  ["contract_count", "계약결과 수"],
  ["contract_amount_krw", "계약금액(원)"],
  ["contract_date", "계약일자"],
  ["procurement_request_name", "조달요청명"],
  ["procurement_request_budget_amount_krw", "조달요청 배정예산(원)"],
  ["procurement_request_representative_amount_krw", "조달요청 대표금액(원)"],
  ["procurement_request_total_service_budget_amount_krw", "총용역예산(원)"],
  ["procurement_request_current_budget_amount_krw", "금차예산(원)"],
  ["procurement_request_order_agency", "조달요청 기관"],
  ["procurement_request_input_date", "조달요청 입력일시"],
  ["participant_data_status", "참여기업 데이터 상태"],
  ["award_data_status", "낙찰 데이터 상태"],
  ["contract_data_status", "계약 데이터 상태"],
  ["procurement_request_data_status", "조달요청 데이터 상태"],
  ["notice_url", "공고 상세 URL"],
  ["source_dataset", "원천 데이터셋"],
  ["source_url", "원천 데이터 URL"],
];

const AWARD_COLUMNS = [
  ["record_id", "공고 고유ID"],
  ["bid_notice_no", "입찰공고번호"],
  ["bid_notice_order", "공고차수"],
  ["contract_process_item_index", "계약과정 항목 순번"],
  ["winner_sequence", "낙찰 순번"],
  ["winner_company", "낙찰기업"],
  ["winner_business_no", "낙찰기업 사업자번호"],
  ["winner_ceo", "대표자"],
  ["award_amount_krw", "낙찰금액(원)"],
  ["award_rate_pct", "낙찰률(%)"],
  ["participant_count", "참가업체 수"],
  ["opening_date", "개찰일시"],
  ["parse_status", "파싱 상태"],
  ["raw_entry", "원문 항목"],
  ["bidwinr_info_list_raw", "낙찰정보 원문 목록"],
  ["exact_order_match_yn", "공고차수 정확매칭"],
  ["link_status", "공고 연결 상태"],
  ["source_dataset", "원천 데이터셋"],
  ["source_url", "원천 데이터 URL"],
];

const CONTRACT_COLUMNS = [
  ["record_id", "공고 고유ID"],
  ["bid_notice_no", "입찰공고번호"],
  ["bid_notice_order", "공고차수"],
  ["contract_process_item_index", "계약과정 항목 순번"],
  ["contract_sequence", "계약 순번"],
  ["contract_no", "계약번호"],
  ["contract_name", "계약명"],
  ["contract_agency", "계약기관"],
  ["contract_demand_agency", "계약 수요기관"],
  ["contract_method", "계약방법"],
  ["contract_amount_krw", "계약금액(원)"],
  ["contract_date", "계약일자"],
  ["parse_status", "파싱 상태"],
  ["raw_entry", "원문 항목"],
  ["contract_info_list_raw", "계약정보 원문 목록"],
  ["exact_order_match_yn", "공고차수 정확매칭"],
  ["link_status", "공고 연결 상태"],
  ["source_dataset", "원천 데이터셋"],
  ["source_url", "원천 데이터 URL"],
];

const REQUEST_COLUMNS = [
  ["procurement_request_no", "조달요청번호"],
  ["linked_record_ids", "연결 공고 고유ID"],
  ["linked_bid_notice_nos", "연결 입찰공고번호"],
  ["linked_bid_notice_orders", "연결 공고차수"],
  ["service_type", "용역구분"],
  ["request_name", "조달요청명"],
  ["budget_amount_krw", "일반용역 배정예산(원)"],
  ["representative_amount_krw", "일반용역 대표금액(원)"],
  ["total_service_budget_amount_krw", "기술용역 총용역예산(원)"],
  ["current_budget_amount_krw", "기술용역 금차예산(원)"],
  ["order_agency", "요청기관"],
  ["input_date", "입력일시"],
  ["request_data_status", "수집 상태"],
  ["source_operation", "API 기능"],
  ["source_dataset", "원천 데이터셋"],
  ["source_url", "원천 데이터 URL"],
];

const BIDDER_COLUMNS = [
  ["record_id", "공고 고유ID"],
  ["bid_notice_no", "입찰공고번호"],
  ["bid_notice_order", "공고차수"],
  ["bid_classification_no", "입찰분류번호"],
  ["rebid_no", "재입찰번호"],
  ["opening_rank", "개찰순위"],
  ["participant_company", "참여기업"],
  ["participant_business_no", "참여기업 사업자번호"],
  ["participant_ceo", "대표자"],
  ["bid_amount_krw", "투찰금액(원)"],
  ["bid_rate_pct", "투찰률(%)"],
  ["bid_date", "투찰일시"],
  ["final_winner_yn", "최종낙찰 여부"],
  ["source_dataset", "원천 데이터셋"],
  ["source_url", "원천 데이터 URL"],
];

const ACCESS_COLUMNS = [
  ["service_id", "서비스 ID"],
  ["service_name", "서비스명"],
  ["dataset_url", "공공데이터포털 URL"],
  ["operation", "API 기능"],
  ["purpose", "수집 목적"],
  ["access_status", "접근 상태"],
  ["error_code", "오류 코드"],
  ["message", "진단 메시지"],
  ["checked_at", "확인일시"],
  ["next_action", "다음 조치"],
];

const DATE_FIELDS = new Set([
  "notice_date",
  "bid_start",
  "bid_close",
  "opening_date",
  "contract_date",
  "procurement_request_input_date",
  "input_date",
  "bid_date",
  "checked_at",
]);

const INTEGER_FIELDS = new Set([
  "notice_year",
  "budget_amount_krw",
  "estimated_price_krw",
  "vat_amount_krw",
  "tracker_score",
  "winner_count",
  "participant_count",
  "contract_count",
  "opening_rank",
  "award_amount_krw",
  "contract_amount_krw",
  "procurement_request_budget_amount_krw",
  "procurement_request_representative_amount_krw",
  "procurement_request_total_service_budget_amount_krw",
  "procurement_request_current_budget_amount_krw",
  "representative_amount_krw",
  "total_service_budget_amount_krw",
  "current_budget_amount_krw",
  "bid_amount_krw",
]);

const DECIMAL_FIELDS = new Set(["award_rate_pct", "bid_rate_pct"]);

const IDENTIFIER_FIELDS = new Set([
  "record_id",
  "bid_notice_no",
  "bid_notice_order",
  "winner_business_no",
  "participant_business_no",
  "bid_classification_no",
  "rebid_no",
  "order_plan_unified_no",
  "pre_spec_registration_no",
  "procurement_request_no",
  "contract_no",
  "contract_process_item_index",
  "winner_sequence",
  "contract_sequence",
  "service_id",
  "error_code",
]);

const OFFICIAL_SOURCES = [
  ["입찰공고정보서비스", "최근 5개년 공고 검색·기본정보", "https://www.data.go.kr/data/15129394/openapi.do"],
  ["조달청 입찰공고 내역", "나라장터 SSO 기반 대량 공고 보고서", "https://www.data.go.kr/data/15053346/fileData.do"],
  ["계약과정통합공개서비스", "낙찰기업·낙찰금액·계약정보 보강", "https://www.data.go.kr/data/15129459/openapi.do"],
  ["조달요청정보서비스", "조달요청·발주계획·예산 정보 보강", "https://www.data.go.kr/data/15129468/openapi.do"],
  ["나라장터 낙찰정보서비스", "실제 참여기업·투찰금액·개찰순위·최종낙찰", "https://www.data.go.kr/data/15129397/openapi.do"],
];


function usage() {
  return [
    "사용법:",
    "  node scripts/build_climate_procurement_workbook.mjs \\",
    "    --input-dir reports \\",
    "    --output outputs/climate_procurement_5y_enriched.xlsx",
    "",
    "선택 인자:",
    "  --notices-csv <경로>    보강된 공고 CSV",
    "  --awards-csv <경로>     낙찰 상세 CSV",
    "  --contracts-csv <경로>  계약 상세 CSV",
    "  --requests-csv <경로>   조달요청 상세 CSV",
    "  --bidders-csv <경로>    참여기업 상세 CSV",
    "  --access-csv <경로>     수집 상태 CSV",
    "  --preview-dir <경로>  시트별 검토용 PNG 저장 위치",
    "  --no-previews          PNG 렌더링 생략",
  ].join("\n");
}


function parseArgs(argv) {
  const options = {
    inputDir: path.resolve(process.cwd(), "reports"),
    output: path.resolve(process.cwd(), "outputs", "climate_procurement_5y_review.xlsx"),
    previewDir: null,
    renderPreviews: true,
    noticesCsv: null,
    awardsCsv: null,
    contractsCsv: null,
    requestsCsv: null,
    biddersCsv: null,
    accessCsv: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      console.log(usage());
      process.exit(0);
    }
    if (arg === "--no-previews") {
      options.renderPreviews = false;
      continue;
    }
    const next = argv[index + 1];
    if ([
      "--input-dir",
      "--output",
      "--preview-dir",
      "--notices-csv",
      "--awards-csv",
      "--contracts-csv",
      "--requests-csv",
      "--bidders-csv",
      "--access-csv",
    ].includes(arg)) {
      if (!next || next.startsWith("--")) {
        throw new Error(`${arg} 뒤에 경로가 필요합니다.`);
      }
      if (arg === "--input-dir") options.inputDir = path.resolve(next);
      if (arg === "--output") options.output = path.resolve(next);
      if (arg === "--preview-dir") options.previewDir = path.resolve(next);
      if (arg === "--notices-csv") options.noticesCsv = path.resolve(next);
      if (arg === "--awards-csv") options.awardsCsv = path.resolve(next);
      if (arg === "--contracts-csv") options.contractsCsv = path.resolve(next);
      if (arg === "--requests-csv") options.requestsCsv = path.resolve(next);
      if (arg === "--bidders-csv") options.biddersCsv = path.resolve(next);
      if (arg === "--access-csv") options.accessCsv = path.resolve(next);
      index += 1;
      continue;
    }
    throw new Error(`알 수 없는 인자입니다: ${arg}`);
  }
  if (path.extname(options.output).toLowerCase() !== ".xlsx") {
    throw new Error("--output 경로는 .xlsx 확장자여야 합니다.");
  }
  if (!options.previewDir) {
    const parsed = path.parse(options.output);
    options.previewDir = path.join(parsed.dir, `${parsed.name}_previews`);
  }
  return options;
}


function columnLetter(index) {
  let value = index + 1;
  let letters = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    letters = String.fromCharCode(65 + remainder) + letters;
    value = Math.floor((value - 1) / 26);
  }
  return letters;
}


function textValue(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}


function numberValue(value) {
  const raw = textValue(value).replaceAll(",", "");
  if (raw === "") return null;
  if (!/^-?\d+(?:\.\d+)?$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}


function dateValue(value) {
  const raw = textValue(value);
  if (!raw) return null;
  const match = raw.match(
    /^(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})(?:(?:[ T]?)(\d{2}):?(\d{2})?:?(\d{2})?)?/,
  );
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4] ?? 0);
  const minute = Number(match[5] ?? 0);
  const second = Number(match[6] ?? 0);
  const result = new Date(year, month - 1, day, hour, minute, second);
  if (
    result.getFullYear() !== year
    || result.getMonth() !== month - 1
    || result.getDate() !== day
  ) {
    return null;
  }
  return result;
}


function localDateText(value) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return "확인 불가";
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}


function typedValue(field, value) {
  const raw = textValue(value);
  if (raw === "") return null;
  if (DATE_FIELDS.has(field)) return dateValue(raw) ?? raw;
  if (INTEGER_FIELDS.has(field) || DECIMAL_FIELDS.has(field)) {
    return numberValue(raw) ?? raw;
  }
  return raw;
}


function parseCsvText(csvText) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let index = 0; index < csvText.length; index += 1) {
    const char = csvText[index];
    if (char === '"') {
      if (inQuotes && csvText[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      row.push(field);
      field = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && csvText[index + 1] === "\n") index += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      continue;
    }
    field += char;
  }
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((values) => values.some((value) => value !== ""));
}


async function readCsvRecords(filePath, requiredFields) {
  const csvText = (await fs.readFile(filePath, "utf8")).replace(/^\uFEFF/, "");
  // artifact-tool validates the CSV structure, while the raw parser below preserves
  // identifiers such as bid order "000" that CSV type inference can coerce to 0.
  const csvWorkbook = await Workbook.fromCSV(csvText, { sheetName: "원본" });
  const rawSheet = csvWorkbook.worksheets.getItem("원본");
  const used = rawSheet.getUsedRange(true);
  const artifactMatrix = used?.values ?? [];
  const matrix = parseCsvText(csvText);
  if (matrix.length === 0) return [];
  if (artifactMatrix.length !== matrix.length) {
    throw new Error(`${path.basename(filePath)}의 CSV 행 해석 결과가 일치하지 않습니다.`);
  }
  const headers = matrix[0].map((value) => textValue(value));
  for (const required of requiredFields) {
    if (!headers.includes(required)) {
      throw new Error(`${path.basename(filePath)}에 필수 열 '${required}'가 없습니다.`);
    }
  }
  return matrix.slice(1)
    .filter((row) => row.some((value) => textValue(value) !== ""))
    .map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
}


function setBaseSheetStyle(sheet) {
  sheet.showGridLines = false;
  sheet.getRange("A1").format.font = { name: FONT_FAMILY, size: 10, color: COLORS.text };
}


function writeSheetHeading(sheet, title, note, columnCount) {
  const lastColumn = columnLetter(Math.max(0, columnCount - 1));
  sheet.mergeCells(`A1:${lastColumn}1`);
  sheet.mergeCells(`A2:${lastColumn}2`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A2").values = [[note]];
  sheet.getRange(`A1:${lastColumn}1`).format = {
    fill: COLORS.navy,
    font: { name: FONT_FAMILY, size: 16, bold: true, color: COLORS.white },
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${lastColumn}2`).format = {
    fill: COLORS.paleBlue,
    font: { name: FONT_FAMILY, size: 10, color: COLORS.text },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange("A1").format.rowHeight = 30;
  sheet.getRange("A2").format.rowHeight = 34;
}


function applyColumnFormatting(sheet, columns, dataRowCount) {
  const finalRow = Math.max(4, dataRowCount + 3);
  for (let index = 0; index < columns.length; index += 1) {
    const [field] = columns[index];
    const letter = columnLetter(index);
    const columnRange = sheet.getRange(`${letter}1:${letter}${finalRow}`);
    let width = 13;
    if (["notice_title", "contract_name", "request_name", "procurement_request_name"].includes(field)) width = 48;
    else if ([
      "notice_agency", "demand_agency", "participant_company", "winner_company",
      "contract_agency", "contract_demand_agency", "order_agency", "procurement_request_order_agency",
    ].includes(field)) width = 22;
    else if (["relevance_reason", "message", "next_action", "raw_entry", "bidwinr_info_list_raw", "contract_info_list_raw"].includes(field)) width = 42;
    else if ([
      "participant_data_status", "award_data_status", "contract_data_status",
      "procurement_request_data_status", "request_data_status", "parse_status", "link_status", "purpose",
    ].includes(field)) width = 31;
    else if (["notice_url", "source_url", "dataset_url"].includes(field)) width = 42;
    else if (["source_dataset", "service_name", "operation", "categories", "search_terms", "matched_keywords"].includes(field)) width = 24;
    else if (DATE_FIELDS.has(field)) width = 19;
    else if (IDENTIFIER_FIELDS.has(field)) width = 20;
    else if (INTEGER_FIELDS.has(field) || DECIMAL_FIELDS.has(field)) width = 16;
    columnRange.format.columnWidth = width;
    if (dataRowCount > 0) {
      const dataRange = sheet.getRange(`${letter}4:${letter}${dataRowCount + 3}`);
      if (DATE_FIELDS.has(field)) dataRange.setNumberFormat("yyyy-mm-dd hh:mm");
      if (INTEGER_FIELDS.has(field)) dataRange.setNumberFormat("#,##0");
      if (DECIMAL_FIELDS.has(field)) dataRange.setNumberFormat("0.00");
      if (IDENTIFIER_FIELDS.has(field)) dataRange.setNumberFormat("@");
    }
  }
}


function addStatusConditionalFormatting(sheet, columns, rowCount) {
  if (rowCount === 0) return;
  for (const field of [
    "relevance_status", "access_status", "final_winner_yn", "parse_status",
    "award_data_status", "contract_data_status", "procurement_request_data_status", "request_data_status",
  ]) {
    const index = columns.findIndex(([name]) => name === field);
    if (index < 0) continue;
    const letter = columnLetter(index);
    const range = sheet.getRange(`${letter}4:${letter}${rowCount + 3}`);
    if (field === "relevance_status") {
      range.conditionalFormats.add("containsText", {
        text: "핵심",
        format: { fill: COLORS.paleGreen, font: { bold: true, color: "#166534" } },
      });
      range.conditionalFormats.add("containsText", {
        text: "검토필요",
        format: { fill: COLORS.paleAmber, font: { color: "#7C5B00" } },
      });
      range.conditionalFormats.add("containsText", {
        text: "제외",
        format: { fill: COLORS.gray, font: { color: "#666666" } },
      });
    } else if (field === "access_status") {
      range.conditionalFormats.add("containsText", {
        text: "사용가능",
        format: { fill: COLORS.paleGreen, font: { bold: true, color: "#166534" } },
      });
      range.conditionalFormats.add("containsText", {
        text: "활용신청필요",
        format: { fill: COLORS.paleAmber, font: { bold: true, color: "#7C5B00" } },
      });
      range.conditionalFormats.add("containsText", {
        text: "부분완료",
        format: { fill: COLORS.paleAmber, font: { bold: true, color: "#7C5B00" } },
      });
    } else if (field === "final_winner_yn") {
      range.conditionalFormats.add("containsText", {
        text: "Y",
        format: { fill: COLORS.paleGreen, font: { bold: true, color: "#166534" } },
      });
    } else {
      range.conditionalFormats.add("containsText", {
        text: "정상",
        format: { fill: COLORS.paleGreen, font: { color: "#166534" } },
      });
      range.conditionalFormats.add("containsText", {
        text: "완료",
        format: { fill: COLORS.paleGreen, font: { color: "#166534" } },
      });
      range.conditionalFormats.add("containsText", {
        text: "오류",
        format: { fill: COLORS.paleRed, font: { color: "#9C0006" } },
      });
    }
  }
}


function writeDataSheet(sheet, title, note, columns, records, tableName, emptyNote = "현재 수집된 행이 없습니다.") {
  setBaseSheetStyle(sheet);
  writeSheetHeading(sheet, title, note, columns.length);
  const headers = columns.map(([, label]) => label);
  const matrix = records.map((record) => columns.map(([field]) => typedValue(field, record[field])));
  sheet.getRangeByIndexes(2, 0, 1, headers.length).values = [headers];
  const headerRange = sheet.getRangeByIndexes(2, 0, 1, headers.length);
  headerRange.format = {
    fill: COLORS.teal,
    font: { name: FONT_FAMILY, size: 10, bold: true, color: COLORS.white },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: "#B7C9D6" },
  };
  headerRange.format.rowHeight = 34;
  if (matrix.length > 0) {
    const dataRange = sheet.getRangeByIndexes(3, 0, matrix.length, headers.length);
    dataRange.values = matrix;
    dataRange.format.font = { name: FONT_FAMILY, size: 9, color: COLORS.text };
    dataRange.format.verticalAlignment = "center";
    dataRange.format.borders = { preset: "all", style: "thin", color: "#E5E7EB" };
    const lastColumn = columnLetter(headers.length - 1);
    const table = sheet.tables.add(`A3:${lastColumn}${matrix.length + 3}`, true, tableName);
    table.style = "TableStyleMedium2";
    table.showFilterButton = true;
    table.showBandedColumns = false;
  } else {
    const lastColumn = columnLetter(headers.length - 1);
    sheet.mergeCells(`A5:${lastColumn}6`);
    sheet.getRange("A5").values = [[emptyNote]];
    sheet.getRange(`A5:${lastColumn}6`).format = {
      fill: COLORS.paleAmber,
      font: { name: FONT_FAMILY, size: 11, bold: true, color: "#7C5B00" },
      wrapText: true,
      verticalAlignment: "center",
      borders: { preset: "outside", style: "thin", color: "#D6B656" },
    };
  }
  applyColumnFormatting(sheet, columns, matrix.length);
  addStatusConditionalFormatting(sheet, columns, matrix.length);
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(Math.min(4, columns.length));
  return matrix.length;
}


function buildSummaryStats(notices, bidders, awards, contracts, requests) {
  const years = new Map();
  const categories = new Map();
  let earliest = null;
  let latest = null;
  let budgetKnownCount = 0;
  let budgetKnownTotal = 0;
  for (const row of notices) {
    const year = numberValue(row.notice_year) ?? dateValue(row.notice_date)?.getFullYear() ?? null;
    if (year !== null) {
      if (!years.has(year)) years.set(year, { total: 0, core: 0, review: 0, excluded: 0, budget: 0, budgetKnown: 0 });
      const item = years.get(year);
      item.total += 1;
      if (textValue(row.relevance_status) === "핵심") item.core += 1;
      else if (textValue(row.relevance_status) === "검토필요") item.review += 1;
      else if (textValue(row.relevance_status).startsWith("제외")) item.excluded += 1;
      const budget = numberValue(row.budget_amount_krw);
      if (budget !== null) {
        item.budget += budget;
        item.budgetKnown += 1;
        budgetKnownCount += 1;
        budgetKnownTotal += budget;
      }
    }
    const published = dateValue(row.notice_date);
    if (published && (!earliest || published < earliest)) earliest = published;
    if (published && (!latest || published > latest)) latest = published;
    const categoryTokens = textValue(row.categories).split(",").map((value) => value.trim()).filter(Boolean);
    for (const category of categoryTokens) {
      if (!categories.has(category)) categories.set(category, { total: 0, core: 0 });
      const item = categories.get(category);
      item.total += 1;
      if (textValue(row.relevance_status) === "핵심") item.core += 1;
    }
  }
  return {
    total: notices.length,
    core: notices.filter((row) => textValue(row.relevance_status) === "핵심").length,
    review: notices.filter((row) => textValue(row.relevance_status) === "검토필요").length,
    excluded: notices.filter((row) => textValue(row.relevance_status).startsWith("제외")).length,
    bidderRows: bidders.length,
    awardRows: awards.length,
    awardNotices: new Set(awards.map((row) => textValue(row.record_id)).filter(Boolean)).size,
    contractRows: contracts.length,
    contractNotices: new Set(contracts.map((row) => textValue(row.record_id)).filter(Boolean)).size,
    requestRows: requests.length,
    winners: notices.filter((row) => textValue(row.winner_company) !== "").length,
    earliest,
    latest,
    budgetKnownCount,
    budgetKnownTotal,
    years: [...years.entries()].sort(([a], [b]) => a - b),
    categories: [...categories.entries()].sort(([, a], [, b]) => b.total - a.total),
  };
}


function addKpiCard(sheet, startColumn, label, value, fill) {
  const left = columnLetter(startColumn);
  const right = columnLetter(startColumn + 1);
  sheet.mergeCells(`${left}5:${right}5`);
  sheet.mergeCells(`${left}6:${right}7`);
  sheet.getRange(`${left}5`).values = [[label]];
  sheet.getRange(`${left}6`).values = [[value]];
  sheet.getRange(`${left}5:${right}5`).format = {
    fill,
    font: { name: FONT_FAMILY, size: 10, bold: true, color: COLORS.text },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#B7C9D6" },
  };
  sheet.getRange(`${left}6:${right}7`).format = {
    fill: COLORS.white,
    font: { name: FONT_FAMILY, size: 20, bold: true, color: COLORS.navy },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    numberFormat: "#,##0",
    borders: { preset: "outside", style: "thin", color: "#B7C9D6" },
  };
}


function buildSummarySheet(sheet, notices, bidders, awards, contracts, requests, accessRows) {
  const stats = buildSummaryStats(notices, bidders, awards, contracts, requests);
  const collectionRun = accessRows.find((row) => textValue(row.service_id) === "collection_run");
  const periodMatch = textValue(collectionRun?.purpose).match(
    /(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})/,
  );
  const queryPeriod = periodMatch
    ? `${periodMatch[1]} ~ ${periodMatch[2]}`
    : `${localDateText(stats.earliest)} ~ ${localDateText(stats.latest)}`;
  setBaseSheetStyle(sheet);
  writeSheetHeading(
    sheet,
    "기후·온실가스·배출권·외부사업 조달공고 검토 대시보드",
    `조회 범위: ${queryPeriod} | 검색결과 공고일: ${localDateText(stats.earliest)} ~ ${localDateText(stats.latest)} | 관련성 판정은 1차 자동분류이므로 핵심·검토필요 건을 사람이 최종 검토하세요.`,
    16,
  );
  addKpiCard(sheet, 0, "전체 고유 공고", stats.total, COLORS.lightTeal);
  addKpiCard(sheet, 2, "핵심", stats.core, COLORS.paleGreen);
  addKpiCard(sheet, 4, "검토필요", stats.review, COLORS.paleAmber);
  addKpiCard(sheet, 6, "낙찰 확인 공고", stats.awardNotices, COLORS.paleBlue);
  addKpiCard(sheet, 8, "낙찰 상세 행", stats.awardRows, COLORS.paleBlue);
  addKpiCard(sheet, 10, "계약 상세 행", stats.contractRows, COLORS.gray);
  addKpiCard(sheet, 12, "조달요청 행", stats.requestRows, COLORS.gray);
  addKpiCard(sheet, 14, "참여기업 행", stats.bidderRows, COLORS.paleAmber);

  const annualHeaders = ["연도", "전체", "핵심", "검토필요", "제외", "배정예산 합계(원)", "예산 확인 건"];
  const annualRows = stats.years.map(([year, item]) => [
    year,
    item.total,
    item.core,
    item.review,
    item.excluded,
    item.budget,
    item.budgetKnown,
  ]);
  sheet.getRange("A10:G10").values = [annualHeaders];
  if (annualRows.length > 0) sheet.getRangeByIndexes(10, 0, annualRows.length, annualHeaders.length).values = annualRows;
  const annualEnd = 10 + annualRows.length;
  sheet.getRange(`A10:G${Math.max(10, annualEnd)}`).format = {
    font: { name: FONT_FAMILY, size: 10, color: COLORS.text },
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
    verticalAlignment: "center",
  };
  sheet.getRange("A10:G10").format = {
    fill: COLORS.teal,
    font: { name: FONT_FAMILY, size: 10, bold: true, color: COLORS.white },
    borders: { preset: "all", style: "thin", color: "#B7C9D6" },
  };
  if (annualRows.length > 0) {
    sheet.getRange(`A11:E${annualEnd}`).setNumberFormat("#,##0");
    sheet.getRange(`F11:F${annualEnd}`).setNumberFormat("#,##0");
    sheet.getRange(`G11:G${annualEnd}`).setNumberFormat("#,##0");
    const annualTable = sheet.tables.add(`A10:G${annualEnd}`, true, "AnnualSummaryTable");
    annualTable.style = "TableStyleMedium2";
    const chart = sheet.charts.add("line", sheet.getRange(`A10:D${annualEnd}`));
    chart.title = "연도별 공고·관련성 판정 추이";
    chart.titleTextStyle.typeface = FONT_FAMILY;
    chart.titleTextStyle.fontSize = 12;
    chart.legend = { position: "top", textStyle: { typeface: FONT_FAMILY, fontSize: 10 } };
    chart.xAxis = { axisType: "textAxis", textStyle: { typeface: FONT_FAMILY, fontSize: 9 } };
    chart.yAxis = {
      numberFormatCode: "#,##0",
      numberFormatSourceLinked: false,
      textStyle: { typeface: FONT_FAMILY, fontSize: 9 },
    };
    chart.setPosition("I10", "P24");
  }

  const categoryStart = Math.max(28, annualEnd + 3);
  sheet.getRange(`A${categoryStart}:C${categoryStart}`).values = [["기후·ESG 분류(복수 분류 중복 가능)", "공고 건수", "핵심 건수"]];
  const categoryRows = stats.categories.length > 0 ? stats.categories.map(([category, item]) => [category, item.total, item.core]) : [["분류 없음", 0, 0]];
  sheet.getRangeByIndexes(categoryStart, 0, categoryRows.length, 3).values = categoryRows;
  const categoryEnd = categoryStart + categoryRows.length;
  sheet.getRange(`A${categoryStart}:C${categoryEnd}`).format = {
    font: { name: FONT_FAMILY, size: 10, color: COLORS.text },
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
  };
  sheet.getRange(`A${categoryStart}:C${categoryStart}`).format = {
    fill: COLORS.teal,
    font: { name: FONT_FAMILY, size: 10, bold: true, color: COLORS.white },
    borders: { preset: "all", style: "thin", color: "#B7C9D6" },
  };
  sheet.getRange(`B${categoryStart + 1}:C${categoryEnd}`).setNumberFormat("#,##0");
  const categoryTable = sheet.tables.add(`A${categoryStart}:C${categoryEnd}`, true, "CategorySummaryTable");
  categoryTable.style = "TableStyleMedium2";

  const accessSummary = accessRows.map((row) => `${textValue(row.service_name)}: ${textValue(row.access_status)}`).join(" | ");
  const noteStart = categoryStart;
  sheet.mergeCells(`E${noteStart}:P${noteStart + 1}`);
  sheet.getRange(`E${noteStart}`).values = [[
    "중요: 이번 파일은 일일 API 호출한도에 따라 일부 공고부터 누적 보강한 결과일 수 있습니다. 공란은 0원이 아니라 ‘미제공·미수집’일 수 있으며, 복수 계약금액은 합산하지 않았습니다. 반드시 ‘수집상태’ 시트를 함께 확인하세요.",
  ]];
  sheet.getRange(`E${noteStart}:P${noteStart + 1}`).format = {
    fill: COLORS.paleAmber,
    font: { name: FONT_FAMILY, size: 11, bold: true, color: "#7C5B00" },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#D6B656" },
  };
  sheet.mergeCells(`E${noteStart + 3}:P${noteStart + 5}`);
  sheet.getRange(`E${noteStart + 3}`).values = [[`수집 상태 요약: ${accessSummary || "수집상태 CSV에 행이 없습니다."}`]];
  sheet.getRange(`E${noteStart + 3}:P${noteStart + 5}`).format = {
    fill: COLORS.gray,
    font: { name: FONT_FAMILY, size: 10, color: COLORS.text },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#B7C9D6" },
  };
  const finalSummaryRow = Math.max(38, categoryEnd, noteStart + 5);
  sheet.getRange(`A1:A${finalSummaryRow}`).format.columnWidth = 18;
  sheet.getRange(`B1:G${finalSummaryRow}`).format.columnWidth = 14;
  sheet.getRange(`H1:H${finalSummaryRow}`).format.columnWidth = 3;
  sheet.getRange(`I1:P${finalSummaryRow}`).format.columnWidth = 13;
  sheet.freezePanes.freezeRows(3);
}


function appendOfficialSources(sheet, accessRowCount) {
  const start = Math.max(9, accessRowCount + 7);
  sheet.mergeCells(`A${start}:J${start}`);
  sheet.getRange(`A${start}`).values = [["공식 데이터 출처와 역할"]];
  sheet.getRange(`A${start}:J${start}`).format = {
    fill: COLORS.navy,
    font: { name: FONT_FAMILY, size: 12, bold: true, color: COLORS.white },
  };
  sheet.getRange(`A${start + 1}:C${start + 1}`).values = [["데이터셋", "이 워크북에서의 역할", "공식 URL"]];
  sheet.getRangeByIndexes(start + 1, 0, OFFICIAL_SOURCES.length, 3).values = OFFICIAL_SOURCES;
  const end = start + 1 + OFFICIAL_SOURCES.length;
  sheet.getRange(`A${start + 1}:C${end}`).format = {
    font: { name: FONT_FAMILY, size: 10, color: COLORS.text },
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(`A${start + 1}:C${start + 1}`).format = {
    fill: COLORS.teal,
    font: { name: FONT_FAMILY, size: 10, bold: true, color: COLORS.white },
    borders: { preset: "all", style: "thin", color: "#B7C9D6" },
  };
  const table = sheet.tables.add(`A${start + 1}:C${end}`, true, "OfficialSourcesTable");
  table.style = "TableStyleMedium2";
  sheet.getRange(`A${start + 2}:A${end}`).format.columnWidth = 28;
  sheet.getRange(`B${start + 2}:B${end}`).format.columnWidth = 39;
  sheet.getRange(`C${start + 2}:C${end}`).format.columnWidth = 48;
}


async function renderPreviews(workbook, previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  const targets = [
    ["요약", "A1:P38", "01_summary.png"],
    ["공고목록", "A1:R14", "02_notices.png"],
    ["공고목록", "AG1:BD14", "02_notices_enrichment.png"],
    ["낙찰결과", "A1:S12", "03_awards.png"],
    ["계약결과", "A1:S12", "04_contracts.png"],
    ["조달요청", "A1:P12", "05_requests.png"],
    ["참여기업", "A1:O12", "06_bidders.png"],
    ["수집상태", "A1:J24", "07_collection_status.png"],
  ];
  for (const [sheetName, range, filename] of targets) {
    const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, filename), new Uint8Array(await preview.arrayBuffer()));
  }
}


async function main() {
  const options = parseArgs(process.argv.slice(2));
  const paths = {
    notices: options.noticesCsv ?? path.join(options.inputDir, "climate_procurement_notices_5y_enriched.csv"),
    awards: options.awardsCsv ?? path.join(options.inputDir, "climate_procurement_awards_5y_enriched.csv"),
    contracts: options.contractsCsv ?? path.join(options.inputDir, "climate_procurement_contracts_5y_enriched.csv"),
    requests: options.requestsCsv ?? path.join(options.inputDir, "climate_procurement_requests_5y_enriched.csv"),
    bidders: options.biddersCsv ?? path.join(options.inputDir, "climate_procurement_bidders_5y_enriched.csv"),
    access: options.accessCsv ?? path.join(options.inputDir, "climate_procurement_access_status_enriched.csv"),
  };
  const [notices, awards, contracts, requests, bidders, accessRows] = await Promise.all([
    readCsvRecords(paths.notices, ["record_id", "notice_title", "notice_date", "relevance_status"]),
    readCsvRecords(paths.awards, ["record_id", "winner_company", "award_amount_krw", "parse_status"]),
    readCsvRecords(paths.contracts, ["record_id", "contract_no", "contract_amount_krw", "parse_status"]),
    readCsvRecords(paths.requests, ["procurement_request_no", "service_type", "request_data_status"]),
    readCsvRecords(paths.bidders, ["record_id", "participant_company", "final_winner_yn"]),
    readCsvRecords(paths.access, ["service_id", "service_name", "access_status"]),
  ]);

  const workbook = Workbook.create();
  const summarySheet = workbook.worksheets.add("요약");
  const noticesSheet = workbook.worksheets.add("공고목록");
  const awardsSheet = workbook.worksheets.add("낙찰결과");
  const contractsSheet = workbook.worksheets.add("계약결과");
  const requestsSheet = workbook.worksheets.add("조달요청");
  const biddersSheet = workbook.worksheets.add("참여기업");
  const accessSheet = workbook.worksheets.add("수집상태");
  summarySheet.tabColor = COLORS.navy;
  noticesSheet.tabColor = COLORS.teal;
  awardsSheet.tabColor = "#5B9BD5";
  contractsSheet.tabColor = "#8064A2";
  requestsSheet.tabColor = "#A5A5A5";
  biddersSheet.tabColor = "#70AD47";
  accessSheet.tabColor = "#ED7D31";

  buildSummarySheet(summarySheet, notices, bidders, awards, contracts, requests, accessRows);
  writeDataSheet(
    noticesSheet,
    "최근 5개년 기후·온실가스·배출권·외부사업 관련 공고",
    "공고명 키워드 검색 결과입니다. ‘관련성 판정’으로 1차 필터링하되, 판정 근거와 원문 공고를 함께 확인하세요. 금액 단위는 원(KRW)입니다.",
    NOTICE_COLUMNS,
    notices,
    "ProcurementNoticesTable",
    "공고 행이 없습니다. 수집기간과 공고 검색 결과를 확인하세요.",
  );
  writeDataSheet(
    awardsSheet,
    "계약과정통합공개서비스 낙찰 상세",
    "낙찰자 한 곳당 한 행입니다. 낙찰금액 단위는 원(KRW)이며, 원문 항목과 공고차수 정확매칭 여부를 함께 보존했습니다.",
    AWARD_COLUMNS,
    awards,
    "ProcurementAwardsTable",
    "이번 누적 보강분에는 낙찰 상세가 없습니다. 수집상태의 계약과정 API 진행률을 확인하세요.",
  );
  writeDataSheet(
    contractsSheet,
    "계약과정통합공개서비스 계약 상세",
    "계약 한 건당 한 행입니다. 같은 공고의 복수 계약은 합산하지 않았으며, 공고목록에는 단일 계약일 때만 계약금액을 표시합니다.",
    CONTRACT_COLUMNS,
    contracts,
    "ProcurementContractsTable",
    "이번 누적 보강분에는 계약 상세가 없습니다. 수집상태의 계약과정 API 진행률을 확인하세요.",
  );
  writeDataSheet(
    requestsSheet,
    "조달요청서비스 상세",
    "일반용역의 배정예산·대표금액과 기술용역의 총용역예산·금차예산은 의미가 달라 별도 열로 보존했습니다. 공고의 기존 예산을 덮어쓰지 않습니다.",
    REQUEST_COLUMNS,
    requests,
    "ProcurementRequestsTable",
    "이번 누적 보강분에는 조달요청 상세가 없습니다. 계약과정에서 조달요청번호가 확인된 공고부터 순차 수집됩니다.",
  );
  writeDataSheet(
    biddersSheet,
    "공고별 실제 참여기업·투찰 내역",
    "이 시트는 나라장터 낙찰정보서비스의 개찰참여기업 데이터를 위한 자리입니다. 최종낙찰은 개찰순위 1위와 다를 수 있으므로 별도 최종낙찰 필드를 확인하세요.",
    BIDDER_COLUMNS,
    bidders,
    "ProcurementBiddersTable",
    "현재 참여기업 상세 행이 없습니다. 계약과정 API는 참가업체 수만 제공하며, 업체별 투찰정보는 나라장터 낙찰정보서비스(15129397) 활용승인 후 수집할 수 있습니다. 공란은 참여기업이 없다는 뜻이 아닙니다.",
  );
  const accessCount = writeDataSheet(
    accessSheet,
    "데이터 수집·API 접근 상태",
    "참여기업·낙찰·계약 데이터의 공란을 해석하기 전에 이 시트를 확인하세요. 오류 코드 30은 공공데이터포털 활용신청/승인이 필요한 경우가 많습니다.",
    ACCESS_COLUMNS,
    accessRows,
    "CollectionAccessTable",
    "수집상태 행이 없습니다. 결과값을 해석하기 전에 실행 로그와 입력 파일을 확인하세요.",
  );
  appendOfficialSources(accessSheet, accessCount);

  workbook.recalculate();
  const summaryCheck = await workbook.inspect({
    kind: "table",
    range: "요약!A1:P38",
    include: "values,formulas",
    tableMaxRows: 38,
    tableMaxCols: 16,
    maxChars: 5000,
  });
  console.log("[verify] summary\n" + summaryCheck.ndjson);
  const noticesCheck = await workbook.inspect({
    kind: "table",
    range: "공고목록!A1:R8",
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 18,
    maxChars: 3500,
  });
  console.log("[verify] notices sample\n" + noticesCheck.ndjson);
  const awardsCheck = await workbook.inspect({
    kind: "table",
    range: "낙찰결과!A1:S8",
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 19,
    maxChars: 4000,
  });
  console.log("[verify] awards sample\n" + awardsCheck.ndjson);
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
    maxChars: 3000,
  });
  console.log("[verify] formula errors\n" + formulaErrors.ndjson);

  if (options.renderPreviews) await renderPreviews(workbook, options.previewDir);
  await fs.mkdir(path.dirname(options.output), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(options.output);

  const saved = await FileBlob.load(options.output);
  const reopened = await SpreadsheetFile.importXlsx(saved);
  const savedCheck = await reopened.inspect({
    kind: "sheet,table",
    include: "id,name",
    tableMaxRows: 2,
    tableMaxCols: 5,
    maxChars: 2500,
  });
  console.log("[verify] saved workbook\n" + savedCheck.ndjson);
  console.log(
    `[done] notices=${notices.length} awards=${awards.length} contracts=${contracts.length} `
    + `requests=${requests.length} bidders=${bidders.length} access_rows=${accessRows.length}`,
  );
  console.log(`[done] workbook=${options.output}`);
  if (options.renderPreviews) console.log(`[done] previews=${options.previewDir}`);
}


main().catch((error) => {
  console.error(`[error] ${error.stack ?? error.message ?? error}`);
  process.exitCode = 1;
});
