import fs from "node:fs/promises";
import path from "node:path";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const FONT = "Arial";
const COLORS = {
  navy: "#14365D",
  teal: "#0F6B78",
  paleBlue: "#EAF2F8",
  paleGreen: "#E3F2E7",
  paleAmber: "#FFF3D6",
  paleRed: "#FBE7E5",
  paleGray: "#F3F6F9",
  line: "#CCD7E3",
  text: "#17202A",
  muted: "#607080",
  white: "#FFFFFF",
};


function usage() {
  return [
    "Usage:",
    "  node scripts/build_rfp_workbench_workbook.mjs",
    "    --input reports/rfp_workbench_data.json",
    "    --output outputs/20260921-rfp-workbench/rfp_workbench_20260921.xlsx",
    "    --preview-dir outputs/20260921-rfp-workbench/previews",
  ].join("\n");
}


function parseArgs(args) {
  const options = { input: "", output: "", previewDir: "" };
  for (let index = 0; index < args.length; index += 1) {
    const value = args[index];
    if (value === "--help" || value === "-h") {
      console.log(usage());
      process.exit(0);
    }
    if (!["--input", "--output", "--preview-dir"].includes(value)) {
      throw new Error("Unknown option: " + value);
    }
    const next = args[index + 1];
    if (!next || next.startsWith("--")) {
      throw new Error(value + " requires a path.");
    }
    if (value === "--input") options.input = path.resolve(next);
    if (value === "--output") options.output = path.resolve(next);
    if (value === "--preview-dir") options.previewDir = path.resolve(next);
    index += 1;
  }
  if (!options.input || !options.output) {
    throw new Error("--input and --output are required.");
  }
  if (path.extname(options.output).toLowerCase() !== ".xlsx") {
    throw new Error("--output must end in .xlsx.");
  }
  if (!options.previewDir) {
    const parsed = path.parse(options.output);
    options.previewDir = path.join(parsed.dir, parsed.name + "_previews");
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


function text(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}


function integer(value) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.round(value);
  const normalized = text(value).replaceAll(",", "");
  return /^-?\d+$/.test(normalized) ? Number(normalized) : null;
}


function asDate(value) {
  const raw = text(value);
  const match = raw.match(/^(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})(?:[ T](\d{2}):?(\d{2})?)?/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4] || 0);
  const minute = Number(match[5] || 0);
  const result = new Date(year, month - 1, day, hour, minute);
  return result.getFullYear() === year && result.getMonth() === month - 1 && result.getDate() === day ? result : null;
}


function tierLabel(value) {
  return {
    tier_1: "Tier 1",
    tier_2: "Tier 2",
    tier_3: "Tier 3",
    unclassified: "미분류",
  }[text(value)] || text(value);
}


function setBaseStyle(sheet) {
  sheet.showGridLines = false;
  sheet.getRange("A1:AZ200").format.font = { name: FONT, size: 10, color: COLORS.text };
  sheet.getRange("A1:AZ200").format.verticalAlignment = "center";
}


function writeHeading(sheet, title, note, endColumn) {
  const end = columnLetter(endColumn - 1);
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: FONT, size: 15, bold: true, color: COLORS.navy };
  sheet.getRange("A3:" + end + "3").format.borders = {
    bottom: { style: "medium", color: COLORS.navy },
  };
  sheet.getRange("A4").values = [[note]];
  sheet.getRange("A4").format = {
    font: { name: FONT, size: 10, italic: true, color: COLORS.muted },
    wrapText: false,
    verticalAlignment: "center",
  };
  sheet.getRange("A4:" + end + "4").format.rowHeight = 20;
}


function styleTable(sheet, headerAddress, dataAddress, tableName) {
  const headerRange = sheet.getRange(headerAddress);
  headerRange.format = {
    fill: COLORS.teal,
    font: { name: FONT, size: 10, bold: true, color: COLORS.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#D7EDF1" },
  };
  headerRange.format.rowHeight = 34;
  const dataRange = sheet.getRange(dataAddress);
  dataRange.format = {
    font: { name: FONT, size: 10, color: COLORS.text },
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.line },
  };
  const table = sheet.tables.add(headerAddress.split(":")[0] + ":" + dataAddress.split(":")[1], true, tableName);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  table.showBandedColumns = false;
}


function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    const letter = columnLetter(index);
    sheet.getRange(letter + "1:" + letter + "200").format.columnWidth = width;
  });
}


function addCard(sheet, startColumn, label, formula, tone) {
  const left = columnLetter(startColumn);
  const right = columnLetter(startColumn + 1);
  sheet.mergeCells(left + "5:" + right + "5");
  sheet.mergeCells(left + "6:" + right + "7");
  sheet.getRange(left + "5").values = [[label]];
  sheet.getRange(left + "6").formulas = [[formula]];
  sheet.getRange(left + "5:" + right + "5").format = {
    fill: tone,
    font: { name: FONT, size: 10, bold: true, color: COLORS.text },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.line },
  };
  sheet.getRange(left + "6:" + right + "7").format = {
    fill: COLORS.white,
    font: { name: FONT, size: 21, bold: true, color: COLORS.navy },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    numberFormat: "#,##0",
    borders: { preset: "outside", style: "thin", color: COLORS.line },
  };
}


function primaryInsight(notice) {
  return notice.primary_insight || {};
}


function noticeRows(notices) {
  return notices.map((notice) => {
    const insight = primaryInsight(notice);
    const attachment = (notice.attachments || [])[0] || {};
    return [
      integer(notice.id),
      tierLabel(notice.business_tier),
      text(notice.tier_reason),
      text(notice.review_status),
      text(notice.title),
      text(notice.buyer),
      text(notice.source_name),
      asDate(notice.published_at),
      asDate(notice.deadline_at),
      text(notice.procurement_method),
      integer(notice.budget_value_krw),
      text(notice.budget),
      text(notice.document_status_label),
      text(insight.task_summary),
      integer(insight.amount_value_krw),
      text(insight.amount_text),
      text(insight.amount_basis),
      text(notice.url),
      text(insight.document_url || attachment.url),
      text(notice.review_note),
    ];
  });
}


function documentRows(documents) {
  return documents.map((document) => [
    integer(document.notice_id),
    tierLabel(document.business_tier),
    text(document.notice_title),
    documentKindLabel(document.document_kind),
    text(document.document_label),
    text(document.file_type),
    text(document.extraction_status_label),
    text(document.task_summary),
    integer(document.amount_value_krw),
    text(document.amount_text),
    text(document.amount_basis),
    text(document.evidence_excerpt),
    text(document.document_url),
    text(document.notice_url),
    text(document.document_access_hint || document.error_message),
    text(document.extracted_at),
  ]);
}


function documentKindLabel(kind) {
  return {
    rfp: "제안요청서",
    scope: "과업지시서",
    notice: "입찰공고문",
    forms: "제출서식",
    pricing: "가격·예산 문서",
    contract: "계약·조건 문서",
    other: "기타 문서",
    missing: "문서 URL 미수집",
  }[text(kind)] || text(kind);
}


function consultingFitLabel(value) {
  return {
    not_reviewed: "미검토",
    high: "높음",
    medium: "보통",
    low: "낮음",
  }[text(value)] || "미검토";
}


function bidDecisionLabel(value) {
  return {
    pending: "미결정",
    bid: "입찰 검토",
    conditional: "조건부 검토",
    no_bid: "미입찰",
  }[text(value)] || "미결정";
}


function fitReviewRows(notices) {
  return notices.map((notice) => {
    const insight = primaryInsight(notice);
    const attachment = (notice.attachments || [])[0] || {};
    const review = notice.fit_review || {};
    return [
      integer(notice.id),
      tierLabel(notice.business_tier),
      text(notice.title),
      text(notice.buyer),
      asDate(notice.deadline_at),
      text(notice.document_status_label),
      consultingFitLabel(review.consulting_fit),
      text(review.qualification_requirements),
      text(review.proposed_team),
      bidDecisionLabel(review.bid_decision),
      text(review.key_risks),
      text(review.decision_note),
      text(notice.url),
      text(insight.document_url || attachment.url),
    ];
  });
}


function buildDashboard(sheet, notices, documents) {
  setBaseStyle(sheet);
  writeHeading(
    sheet,
    "기후·온실가스·배출권거래제 공고 검토 대시보드",
    "원문 링크와 문서 금액의 기준을 함께 확인하세요. 최종 입찰 판단은 담당자가 합니다.",
    15,
  );
  const noticeEnd = Math.max(7, notices.length + 6);
  const documentEnd = Math.max(7, documents.length + 6);
  addCard(sheet, 0, "전체 공고", "=COUNTA('공고목록'!$A$7:$A$" + noticeEnd + ")", COLORS.paleBlue);
  addCard(sheet, 3, "Tier 1", "=COUNTIFS('공고목록'!$B$7:$B$" + noticeEnd + ",\"Tier 1\")", COLORS.paleGreen);
  addCard(sheet, 6, "Tier 2", "=COUNTIFS('공고목록'!$B$7:$B$" + noticeEnd + ",\"Tier 2\")", COLORS.paleAmber);
  addCard(sheet, 9, "Tier 3", "=COUNTIFS('공고목록'!$B$7:$B$" + noticeEnd + ",\"Tier 3\")", COLORS.paleGray);
  addCard(sheet, 12, "공개 원문 추출 완료", "=COUNTIFS('문서요약'!$G$7:$G$" + documentEnd + ",\"공개 원문 추출 완료\")", COLORS.paleGreen);

  const tierHeaders = ["Tier", "공고 수", "공개 문서 추출 완료"];
  const tierRows = [["Tier 1"], ["Tier 2"], ["Tier 3"]];
  sheet.getRange("A11:C11").values = [tierHeaders];
  sheet.getRange("A12:A14").values = tierRows;
  sheet.getRange("B12").formulas = [["=COUNTIFS('공고목록'!$B$7:$B$" + noticeEnd + ",A12)"]];
  sheet.getRange("B12:B14").fillDown();
  sheet.getRange("C12").formulas = [["=COUNTIFS('문서요약'!$B$7:$B$" + documentEnd + ",A12,'문서요약'!$G$7:$G$" + documentEnd + ",\"공개 원문 추출 완료\")"]];
  sheet.getRange("C12:C14").fillDown();
  styleTable(sheet, "A11:C11", "A12:C14", "TierSummaryTable");
  sheet.getRange("B12:C14").setNumberFormat("#,##0");
  const chart = sheet.charts.add("bar", sheet.getRange("A11:B14"));
  chart.title = "Tier별 공고 수";
  chart.titleTextStyle.typeface = FONT;
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = false;
  chart.xAxis = { axisType: "textAxis", textStyle: { typeface: FONT, fontSize: 10 } };
  chart.yAxis = {
    numberFormatCode: "#,##0",
    numberFormatSourceLinked: false,
    textStyle: { typeface: FONT, fontSize: 10 },
  };
  chart.setPosition("E10", "L24");

  sheet.getRange("A17:C17").values = [["금액 필드", "의미", "사용 시 유의사항"]];
  sheet.getRange("A18:C22").values = [
    ["공고목록 금액", "나라장터 목록 API 등이 제공한 금액", "예산 또는 공고금액일 수 있으므로 원문 확인"],
    ["예산액·소요예산", "발주처가 문서에 명시한 사업 예산", "최종 낙찰/계약금액과 다를 수 있음"],
    ["추정가격·기초금액", "입찰 절차상 기준 금액", "VAT 포함 여부와 적용 범위 확인"],
    ["투찰금액", "참여기업이 제출한 가격", "낙찰 여부와 함께 확인"],
    ["계약금액", "계약 체결 후 금액", "실제 계약정보 수집 여부 확인"],
  ];
  styleTable(sheet, "A17:C17", "A18:C22", "AmountGuideTable");
  sheet.getRange("A18:C22").format.wrapText = true;
  sheet.getRange("A18:C22").format.rowHeight = 34;
  setWidths(sheet, [22, 34, 48, 3, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14]);
}


function buildFitReviewSheet(sheet, notices) {
  setBaseStyle(sheet);
  writeHeading(
    sheet,
    "입찰 적합성 검토표",
    "노란색 열은 담당자 입력 영역입니다. 원문 공고·RFP를 확인한 뒤 기록하며, 이 시트의 값은 자동 입찰 판단이 아닙니다.",
    14,
  );
  const headers = [
    "공고 ID", "Tier", "공고명", "발주기관", "마감일", "문서 상태",
    "컨설팅 적합성", "필요 자격·등록", "예상 투입인력", "입찰 의견",
    "핵심 위험·확인사항", "검토 메모", "공식 공고 URL", "대표 RFP/과업지시서 URL",
  ];
  const rows = fitReviewRows(notices);
  const end = Math.max(7, rows.length + 6);
  sheet.getRange("A6:N6").values = [headers];
  if (rows.length) sheet.getRange("A7:N" + end).values = rows;
  styleTable(sheet, "A6:N6", "A7:N" + end, "BidFitReviewTable");
  sheet.getRange("E7:E" + end).setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.getRange("G7:L" + end).format.fill = COLORS.paleAmber;
  sheet.getRange("G7:L" + end).format.wrapText = true;
  sheet.getRange("C7:C" + end).format.wrapText = true;
  sheet.getRange("A7:N" + end).format.rowHeight = 58;
  sheet.getRange("G7:G" + end).dataValidation = {
    rule: { type: "list", values: ["미검토", "높음", "보통", "낮음"] },
  };
  sheet.getRange("J7:J" + end).dataValidation = {
    rule: { type: "list", values: ["미결정", "입찰 검토", "조건부 검토", "미입찰"] },
  };
  setWidths(sheet, [10, 11, 48, 22, 18, 25, 16, 33, 31, 17, 40, 42, 50, 54]);
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(3);
}


function buildNoticesSheet(sheet, notices) {
  setBaseStyle(sheet);
  writeHeading(
    sheet,
    "공고목록",
    "대표 문서만 표시합니다. 복수 문서의 근거와 원문은 문서요약 시트에서 확인하세요.",
    20,
  );
  const headers = [
    "공고 ID", "Tier", "Tier 판단 근거", "검토상태", "공고명", "발주기관", "출처",
    "공고일", "마감일", "입찰방식", "공고목록 금액(원)", "공고목록 금액 원문",
    "문서 상태", "과업 간단 요약", "문서 추출 금액(원)", "문서 금액 원문",
    "금액 기준", "공식 공고 URL", "대표 RFP/과업지시서 URL", "검토 메모",
  ];
  const rows = noticeRows(notices);
  const end = Math.max(7, rows.length + 6);
  sheet.getRange("A6:T6").values = [headers];
  if (rows.length) sheet.getRange("A7:T" + end).values = rows;
  styleTable(sheet, "A6:T6", "A7:T" + end, "WorkbenchNoticesTable");
  sheet.getRange("H7:I" + end).setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.getRange("K7:K" + end).setNumberFormat("#,##0");
  sheet.getRange("O7:O" + end).setNumberFormat("#,##0");
  sheet.getRange("C7:C" + end).format.wrapText = true;
  sheet.getRange("E7:E" + end).format.wrapText = true;
  sheet.getRange("N7:N" + end).format.wrapText = true;
  sheet.getRange("T7:T" + end).format.wrapText = true;
  sheet.getRange("A7:T" + end).format.rowHeight = 52;
  setWidths(sheet, [10, 11, 28, 14, 52, 22, 24, 18, 18, 18, 18, 22, 24, 58, 18, 18, 16, 48, 48, 28]);
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(5);
}


function buildDocumentsSheet(sheet, documents) {
  setBaseStyle(sheet);
  writeHeading(
    sheet,
    "문서요약",
    "문서 한 건당 한 행입니다. 빈 값은 추측하지 않았으므로 상태와 원문 URL을 확인하세요.",
    16,
  );
  const headers = [
    "공고 ID", "Tier", "공고명", "문서 유형", "문서명", "파일 형식", "추출 상태",
    "과업 간단 요약", "문서 추출 금액(원)", "금액 원문", "금액 기준", "근거 문장",
    "문서 URL", "공식 공고 URL", "접근/오류 안내", "추출시각",
  ];
  const rows = documentRows(documents);
  const end = Math.max(7, rows.length + 6);
  sheet.getRange("A6:P6").values = [headers];
  if (rows.length) sheet.getRange("A7:P" + end).values = rows;
  styleTable(sheet, "A6:P6", "A7:P" + end, "DocumentSummaryTable");
  sheet.getRange("I7:I" + end).setNumberFormat("#,##0");
  sheet.getRange("P7:P" + end).setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.getRange("C7:C" + end).format.wrapText = true;
  sheet.getRange("H7:H" + end).format.wrapText = true;
  sheet.getRange("L7:L" + end).format.wrapText = true;
  sheet.getRange("O7:O" + end).format.wrapText = true;
  sheet.getRange("A7:P" + end).format.rowHeight = 66;
  setWidths(sheet, [10, 11, 47, 20, 38, 13, 27, 60, 18, 18, 16, 58, 54, 52, 42, 21]);
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(3);
}


function buildSourcesSheet(sheet, notices, documents) {
  setBaseStyle(sheet);
  writeHeading(
    sheet,
    "출처안내",
    "최종 입찰 판단 전, 공식 공고와 RFP·과업지시서의 원문을 반드시 확인하세요.",
    6,
  );
  const sourceRows = [
    ["나라장터", "공고 목록 및 원문 파일첨부", "https://www.g2b.go.kr/", "목록 API에 첨부 URL이 없으면 원문 파일첨부를 직접 확인"],
    ["온실가스종합정보센터", "GIR 입찰공고 및 직접 공개 HWPX", "https://www.gir.go.kr/", "공개 HWPX만 자동 요약 및 금액 근거 추출"],
    ["자동 추출 범위", "직접 공개된 HWPX", "", "로그인, CAPTCHA, 권한 제한 문서는 우회하지 않음"],
  ];
  const sourceNames = Array.from(new Set(notices.map((notice) => text(notice.source_name)).filter(Boolean)));
  sourceNames.forEach((sourceName) => {
    sourceRows.push([sourceName, "현재 공고 데이터 출처", "", "공고목록 시트의 공식 공고 URL을 확인"]);
  });
  sheet.getRange("A6:D6").values = [["출처", "역할", "기준 URL", "확인 방법"]];
  sheet.getRange("A7:D" + (sourceRows.length + 6)).values = sourceRows;
  styleTable(sheet, "A6:D6", "A7:D" + (sourceRows.length + 6), "SourcesTable");
  sheet.getRange("A7:D" + (sourceRows.length + 6)).format.wrapText = true;
  sheet.getRange("A7:D" + (sourceRows.length + 6)).format.rowHeight = 38;

  const statusStart = sourceRows.length + 10;
  sheet.getRange("A" + statusStart + ":C" + statusStart).values = [["문서 상태", "의미", "현재 건수"]];
  const statusCounts = new Map();
  documents.forEach((document) => {
    const label = text(document.extraction_status_label);
    statusCounts.set(label, (statusCounts.get(label) || 0) + 1);
  });
  const statusRows = Array.from(statusCounts.entries()).map(([label, count]) => [
    label,
    "문서요약 시트의 접근·오류 안내를 함께 확인",
    count,
  ]);
  if (statusRows.length) sheet.getRange("A" + (statusStart + 1) + ":C" + (statusStart + statusRows.length)).values = statusRows;
  styleTable(
    sheet,
    "A" + statusStart + ":C" + statusStart,
    "A" + (statusStart + 1) + ":C" + Math.max(statusStart + 1, statusStart + statusRows.length),
    "DocumentStatusTable",
  );
  sheet.getRange("C" + (statusStart + 1) + ":C" + (statusStart + statusRows.length)).setNumberFormat("#,##0");
  setWidths(sheet, [28, 40, 52, 52, 3, 3]);
  sheet.freezePanes.freezeRows(6);
}


async function renderPreviews(workbook, previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  const targets = [
    ["대시보드", "A1:N24", "01_dashboard.png"],
    ["공고목록", "A1:T14", "02_notices.png"],
    ["문서요약", "A1:P14", "03_documents.png"],
    ["출처안내", "A1:D22", "04_sources.png"],
    ["입찰적합성검토", "A1:N14", "05_bid_fit_review.png"],
  ];
  for (const [sheetName, range, fileName] of targets) {
    const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(path.join(previewDir, fileName), new Uint8Array(await preview.arrayBuffer()));
  }
}


async function main() {
  const options = parseArgs(process.argv.slice(2));
  const payload = JSON.parse(await fs.readFile(options.input, "utf8"));
  const notices = Array.isArray(payload.notices) ? payload.notices : [];
  const documents = Array.isArray(payload.documents) ? payload.documents : [];

  const workbook = Workbook.create();
  const dashboard = workbook.worksheets.add("대시보드");
  const noticesSheet = workbook.worksheets.add("공고목록");
  const documentsSheet = workbook.worksheets.add("문서요약");
  const sourcesSheet = workbook.worksheets.add("출처안내");
  const fitReviewSheet = workbook.worksheets.add("입찰적합성검토");
  dashboard.tabColor = COLORS.navy;
  noticesSheet.tabColor = COLORS.teal;
  documentsSheet.tabColor = "#2B7A4B";
  sourcesSheet.tabColor = "#7A8793";
  fitReviewSheet.tabColor = "#B7791F";

  buildDashboard(dashboard, notices, documents);
  buildNoticesSheet(noticesSheet, notices);
  buildDocumentsSheet(documentsSheet, documents);
  buildSourcesSheet(sourcesSheet, notices, documents);
  buildFitReviewSheet(fitReviewSheet, notices);

  workbook.recalculate();
  const dashboardCheck = await workbook.inspect({
    kind: "table",
    range: "대시보드!A1:N24",
    include: "values,formulas",
    tableMaxRows: 24,
    tableMaxCols: 14,
  });
  console.log(dashboardCheck.ndjson);
  const fitReviewCheck = await workbook.inspect({
    kind: "table",
    range: "입찰적합성검토!A1:N14",
    include: "values,formulas",
    tableMaxRows: 14,
    tableMaxCols: 14,
  });
  console.log(fitReviewCheck.ndjson);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
  });
  console.log(errors.ndjson);

  await renderPreviews(workbook, options.previewDir);
  await fs.mkdir(path.dirname(options.output), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(options.output);
  console.log("Workbook written: " + options.output);
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
