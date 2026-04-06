const NOTION_VERSION = "2022-06-28";
const DB = {
  chat: "ffca8c9b-4a27-4cda-baf0-608030f27e2f",
  death: "20e5277e-b835-8073-8ec7-ca48e136df90"
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/health")
      return new Response(JSON.stringify({status:"ok",bot:"도방 도비 v7"}),{headers:{"Content-Type":"application/json"}});
    if (request.method==="POST"&&(url.pathname==="/kakao"||url.pathname==="/kakao/openbuilder")){
      const body = await request.json().catch(()=>({}));
      const msg = body?.userRequest?.utterance || body?.message || "";
      const ts = new Date().toISOString();
      if (msg) ctx.waitUntil(process(msg, ts, env));
      return new Response(JSON.stringify({version:"2.0",template:{outputs:[{simpleText:{text:"✅ 도비가 기록했습니다!"}}]}}),{headers:{"Content-Type":"application/json"}});
    }
    return new Response("도방 도비 v7",{status:200});
  }
};

// ─────────────────────────────────────────────
// 도방육종 돈사 구조 정의
// ─────────────────────────────────────────────
const LOCATION_MAP = [
  // 영문 코드 (B4.3, A1, C2 등)
  { pattern: /([A-Za-z]{1,2})\s*(\d+)\s*[.\-]?\s*(\d*)/i, type: "code" },
  // 분만사 계열
  { pattern: /분만\s*(\d*)/i, name: "분만사" },
  // 인큐(베이터) 계열
  { pattern: /인큐\s*(\d*)|인큐베이터\s*(\d*)/i, name: "인큐" },
  // 자돈 계열
  { pattern: /자돈\s*(\d*)/i, name: "자돈사" },
  // 비육 계열
  { pattern: /비육\s*(\d*)/i, name: "비육사" },
  // 환돈 계열
  { pattern: /환돈|환자\s*돈/i, name: "환돈사(B4우)" },
  // 돈궁/돈사 일반
  { pattern: /돈궁\s*(\d*)/i, name: "돈궁" },
  // 임신사
  { pattern: /임신\s*(\d*)/i, name: "임신사" },
  // 웅돈사
  { pattern: /웅돈\s*(\d*)/i, name: "웅돈사" },
];

// 발신자 매핑
const SENDER_MAP = {
  "썬": ["썬", "sun", "선"],
  "콰": ["콰", "kwa", "콰이"],
  "여준모": ["준모", "대표", "여준모"],
};

function parseLocation(msg) {
  // 영문코드 먼저 (B4.3, A1 등)
  const codeMatch = msg.match(/([A-Za-z]{1,2})\s*(\d+)\s*[.\-]?\s*(\d+)?/i);
  if (codeMatch) {
    const loc = codeMatch[1].toUpperCase() + codeMatch[2] + (codeMatch[3] ? "." + codeMatch[3] : "");
    return loc;
  }
  // 한글 위치
  for (const def of LOCATION_MAP.slice(1)) {
    const m = msg.match(def.pattern);
    if (m) {
      const num = (m[1] || m[2] || "").trim();
      return def.name + (num ? " " + num : "");
    }
  }
  return "위치미상";
}

function parseCount(msg) {
  // "N두", "N마리", "N마" 등
  const m = msg.match(/(\d+)\s*(두|마리|마|頭)/);
  if (m) return parseInt(m[1]);
  // 숫자만 있으면
  const nums = msg.match(/\d+/g);
  if (nums) return parseInt(nums[nums.length - 1]);
  return 1;
}

function parseSender(msg) {
  for (const [key, aliases] of Object.entries(SENDER_MAP)) {
    for (const alias of aliases) {
      if (msg.includes(alias)) return key;
    }
  }
  return "기타";
}

function classify(msg) {
  if (/폐사|죽|사망|뒤짐|폐사됨/.test(msg)) return "폐사";
  if (/이동|옮|전동|이사|이송/.test(msg)) return "이동";
  if (/출하|출하됨|출하완료/.test(msg)) return "출하";
  if (/사료|급이|밥|먹이/.test(msg)) return "사료";
  if (/백신|접종|주사/.test(msg)) return "백신";
  if (/완료|보고|확인|처리|작업|청소|세척/.test(msg)) return "업무보고";
  if (/이상|고장|누수|냄새|경보/.test(msg)) return "시설이상";
  return "기타";
}

async function process(msg, ts, env) {
  const today = ts.split("T")[0];
  const token = env.NOTION_TOKEN;
  const type = classify(msg);
  const sender = parseSender(msg);

  // 1. 채팅 로그 저장
  await notionCreate(DB.chat, {
    "메시지": {title:[{text:{content:msg}}]},
    "발신시각": {date:{start:ts}},
    "발신자": {select:{name:sender}},
    "분류": {select:{name:type}},
    "원문": {rich_text:[{text:{content:msg}}]},
    "처리상태": {select:{name:type==="기타"?"미처리":"자동처리완료"}}
  }, token);

  // 2. 폐사 → 폐사 기록 DB
  if (type === "폐사") {
    const loc = parseLocation(msg);
    const cnt = parseCount(msg);
    await notionCreate(DB.death, {
      "기록 ID": {title:[{text:{content:loc+" 폐사 "+today}}]},
      "돈사위치": {rich_text:[{text:{content:loc}}]},
      "두수": {number:cnt},
      "원문메시지": {rich_text:[{text:{content:msg}}]},
      "처리상태": {select:{name:"미확인"}},
      "처리자": {select:{name:sender==="기타"?"기타":sender}},
      "발생일": {date:{start:today}}
    }, token);
  }
}

async function notionCreate(dbId, properties, token) {
  const resp = await fetch("https://api.notion.com/v1/pages", {
    method:"POST",
    headers:{"Authorization":"Bearer "+token,"Notion-Version":NOTION_VERSION,"Content-Type":"application/json"},
    body:JSON.stringify({parent:{database_id:dbId},properties})
  });
  if (!resp.ok) console.error("Notion 실패 ["+dbId+"]:", await resp.text());
  else console.log("Notion 성공 ["+dbId+"] type:", Object.keys(properties)[0]);
}
