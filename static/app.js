/* Page state and user actions. Rendering lives in decision-view.js. */
import { request } from "./api-client.js";
import {
  escapeHtml as e,
  constraintsView,
  merchantCards,
  detailsView,
  choiceView,
  comparisonView,
} from "./decision-view.js";

const root = document.getElementById("app");
const dialog = document.getElementById("merchant-dialog");
const detail = document.getElementById("merchant-detail");
const state = {
  page: "decision",
  catalogStats: null,
  result: null,
  history: [],
  saved: new Set(),
  compared: new Map(),
  seen: new Set(),
  selected: null,
  busy: false,
  directory: [],
  directoryTotal: 0,
  directoryPage: 0,
  keyword: "",
  district: "",
};
let toastTimer;
let pageVersion = 0;

function toast(message) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("visible"), 3500);
}

function renderTray() {
  const tray = document.getElementById("compare-tray");
  tray.hidden = !state.compared.size;
  tray.innerHTML = `<span>已选 ${state.compared.size}/3 家</span><button class="button-primary" data-open-compare ${state.compared.size < 2 ? "disabled" : ""}>对比一下</button><button data-clear-compare>清空</button>`;
  document.getElementById("saved-count").textContent = state.saved.size;
}

function catalogSummary() {
  const stats = state.catalogStats;
  if (!stats) return '<p class="source-note">正在读取真实资料库统计…</p>';
  return `<p class="catalog-summary" data-catalog-count="${stats.public_total}">真实资料 ${stats.public_total} 家 · 有坐标 ${stats.mapped_total} 家 · 有来源菜品单价 ${stats.priced_menu_items} 条（${stats.priced_merchant_total} 家，其中有坐标 ${stats.priced_mapped_total} 家）</p>
    <p class="source-note">资料范围为近五年。原归档与本次采集日期分别标注，缺失的价格、营业和地址不补造。</p>`;
}

function renderDecision() {
  window.NightFindWuhanMap?.dispose();
  const result = state.result;
  root.innerHTML = `<section class="page-intro"><span class="eyebrow">从想吃什么，到决定去哪</span><h1>今晚，选一家适合的店。</h1>
    <p>直接问店名、菜单或价格，也可以说明人数、预算、位置和时间。对话与地图查询同一个真实商家库。</p>${catalogSummary()}</section>
    <section class="decision-input"><h2>说说你的打算</h2>
      <div id="conversation-log" aria-live="polite">${state.history
        .slice(-6)
        .map(
          (entry) =>
            `<p class="conversation-${entry.role}"><strong>${entry.role === "user" ? "你" : "夜寻"}：</strong>${e(entry.text)}</p>`,
        )
        .join("")}</div>
      <form id="decision-form"><label class="sr-only" for="request-message">你的用餐需求</label><textarea id="request-message" name="message" maxlength="2000" required placeholder="例如：今晚七点，四个人在江汉路附近，总共三百元，想吃湖北菜。" ${state.busy ? "disabled" : ""}></textarea>
        <div class="card-actions"><button class="button-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "正在整理…" : "帮我挑选"}</button><button type="button" data-location ${state.busy ? "disabled" : ""}>使用当前位置</button><button type="button" data-reset ${state.busy ? "disabled" : ""}>重新开始</button></div></form>
      <div class="quick-actions">${(result?.follow_up?.actions || ["武汉有哪些真实商家", "有哪些咖啡店", "查金贵源的菜单价格"]).map((message) => `<button data-message="${e(message)}" ${state.busy ? "disabled" : ""}>${e(message)}</button>`).join("")}</div>
      <p class="source-note">${result?.mode === "ai" ? "本轮由 AI 提取条件，门店事实来自资料库。" : result?.mode === "fallback" ? "AI 暂不可用，本轮使用本地条件解析。" : "本地条件解析可直接使用；配置 AI 后可理解更灵活的表达。"}</p>
    </section>
    <section class="conditions" aria-label="已理解的条件"><h2>目前理解的需求</h2>${constraintsView(result?.constraints, result?.budget_per_person)}</section>
    <section id="selected-place" ${state.selected ? "" : "hidden"}>${state.selected ? choiceView(state.selected) : ""}</section>
    ${
      result
        ? `<section aria-live="polite"><h2>${result.stage === "clarify" ? "先确认一下" : result.stage === "catalog" ? "真实资料库查询结果" : "这次的候选"}</h2><p class="reply-text">${e(result.reply)}</p>
      ${result.items.length ? `<div class="decision-grid">${merchantCards(result.items, state.saved, state.compared, true)}</div><div class="map-controls"><button data-show-map>在地图上看这几家</button></div><div id="decision-map" class="decision-map" hidden></div>` : ""}
      ${
        Object.keys(result.excluded).length
          ? `<details><summary>为什么有些门店没有入选？</summary><ul>${Object.entries(
              result.excluded,
            )
              .map(([reason, count]) => `<li>${e(reason)}：${count} 家</li>`)
              .join("")}</ul></details>`
          : ""
      }</section>`
        : ""
    }`;
  document
    .getElementById("decision-form")
    .addEventListener("submit", (event) => {
      event.preventDefault();
      sendMessage(new FormData(event.currentTarget).get("message"));
    });
}

async function sendMessage(message, location) {
  if (state.busy) return;
  state.busy = true;
  state.history.push({ role: "user", text: message });
  renderDecision();
  try {
    const result = await request("/api/decision", {
      message,
      context: state.result?.constraints || {},
      location,
      previous_ids: state.result?.items.map((item) => item.id) || [],
      seen_ids: Array.from(state.seen),
      keep_ids:
        state.result?.items
          .filter((item) => item.kept)
          .map((item) => item.id) || [],
    });
    // Start a fresh rotation when the actual constraints change.
    if (
      JSON.stringify(result.constraints) !==
      JSON.stringify(state.result?.constraints)
    )
      state.seen.clear();
    result.items.forEach((item) => state.seen.add(item.id));
    state.result = result;
    if (result.catalog_stats) state.catalogStats = result.catalog_stats;
    state.history.push({ role: "assistant", text: result.reply });
    state.selected = null;
  } catch (error) {
    state.history.push({ role: "assistant", text: error.message });
    if (state.result)
      state.result = {
        ...state.result,
        items: [],
        reply: error.message,
        eligible_total: 0,
        excluded: {},
      };
    toast(error.message);
  } finally {
    state.busy = false;
    if (state.page === "decision") renderDecision();
  }
}

async function renderDirectory(version) {
  root.innerHTML = `<section class="page-intro"><h1>${state.page === "saved" ? "今晚清单" : "真实商家资料"}</h1><p>全部资料来自真实网上门店记录；网上收录不证明当前营业。菜单单价有来源才展示。</p>${catalogSummary()}</section>
    ${state.page === "directory" ? `<form id="directory-form" class="directory-search"><label>店名、菜系或地址<input name="keyword" value="${e(state.keyword)}" maxlength="80"></label><label>行政区<input name="district" value="${e(state.district)}" placeholder="例如：江汉区"></label><button class="button-primary">搜索</button></form>` : ""}
    ${state.page === "directory" ? '<section class="directory-map-section"><h2>真实商家地图</h2><p id="directory-map-status">正在加载全部来源坐标…</p><div id="directory-map" class="decision-map" role="region" aria-label="武汉真实商家地图"></div><p class="source-note">地图展示当前筛选下全部有坐标的门店，不受下方列表分页限制。OSM 社区点位和网页收录均不代表实时营业。</p></section>' : ""}
    <div id="directory-results" class="decision-grid"><p>正在读取门店资料…</p></div><div id="directory-pagination" class="card-actions"></div>`;
  const form = document.getElementById("directory-form");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    state.keyword = data.get("keyword");
    state.district = data.get("district");
    state.directoryPage = 0;
    navigate("directory");
  });
  try {
    const query = new URLSearchParams({
      keyword: state.keyword,
      district: state.district,
      limit: "30",
      offset: String(state.directoryPage * 30),
    });
    const [listResult, mapResult] = await Promise.allSettled([
      request(
        state.page === "saved"
          ? "/api/real-favorites"
          : `/api/real-merchants?${query}`,
      ),
      state.page === "directory"
        ? request(
            `/api/real-map?${new URLSearchParams({ keyword: state.keyword, district: state.district })}`,
          )
        : Promise.resolve(null),
    ]);
    if (version !== pageVersion) return;
    if (listResult.status === "rejected") throw listResult.reason;
    const response = listResult.value;
    if (state.page === "directory") {
      const container = document.getElementById("directory-map");
      const status = document.getElementById("directory-map-status");
      if (mapResult.status === "fulfilled") {
        const mapped = mapResult.value;
        const drawn = window.NightFindWuhanMap?.draw(container, mapped.items);
        container.dataset.pins = drawn?.pins || 0;
        status.textContent = `筛选命中 ${mapped.total} 家，地图标注 ${drawn?.pins || 0} 家有来源坐标的门店。`;
      } else status.textContent = "地图资料暂不可用，仍可浏览下方列表。";
    }
    if (version !== pageVersion) return;
    state.directory = response.items;
    state.directoryTotal = response.total || 0;
    document.getElementById("directory-results").innerHTML = merchantCards(
      response.items,
      state.saved,
      state.compared,
    );
    if (state.page === "directory" && response.total > 30) {
      document.getElementById("directory-pagination").innerHTML =
        `<button data-directory-page="${state.directoryPage - 1}" ${state.directoryPage === 0 ? "disabled" : ""}>上一页</button><span>第 ${state.directoryPage + 1} 页 · 共 ${response.total} 家</span><button data-directory-page="${state.directoryPage + 1}" ${(state.directoryPage + 1) * 30 >= response.total ? "disabled" : ""}>下一页</button>`;
    }
  } catch (error) {
    if (version === pageVersion)
      document.getElementById("directory-results").textContent = error.message;
  }
}

function navigate(page) {
  state.page = page;
  pageVersion += 1;
  window.NightFindWuhanMap?.dispose();
  document
    .querySelectorAll("[data-page]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.page === page),
    );
  if (page === "decision") renderDecision();
  else renderDirectory(pageVersion);
  renderTray();
}

async function merchantById(id) {
  const detail = await request(`/api/real-merchants/${id}`);
  const candidate = state.result?.items.find((item) => item.id === id);
  return {
    ...detail,
    ...(candidate
      ? {
          questions: candidate.questions,
          distance_km: candidate.distance_km,
          reasons: candidate.reasons,
          estimated_total: candidate.estimated_total,
        }
      : {}),
  };
}

async function choose(id) {
  state.selected = await merchantById(id);
  dialog.close();
  navigate("decision");
  document
    .getElementById("selected-place")
    .scrollIntoView({ behavior: "smooth", block: "center" });
}

async function toggleSave(id) {
  const active = !state.saved.has(id);
  await request("/api/real-favorites", { merchant_id: id, active });
  if (active) state.saved.add(id);
  else state.saved.delete(id);
  toast(active ? "已保存到今晚清单" : "已取消收藏");
  navigate(state.page);
}

async function toggleCompare(id) {
  if (state.compared.has(id)) state.compared.delete(id);
  else {
    if (state.compared.size >= 3) return toast("最多比较三家，请先取消一项。");
    state.compared.set(id, await merchantById(id));
  }
  navigate(state.page);
}

async function openComparison() {
  if (state.compared.size < 2) return;
  const ids = Array.from(state.compared.keys());
  const result = await request(`/api/real-compare?ids=${ids.join(",")}`);
  const items = result.items.map((item) => ({
    ...item,
    ...{
      distance_km: state.result?.items.find(
        (candidate) => candidate.id === item.id,
      )?.distance_km,
      questions: state.result?.items.find(
        (candidate) => candidate.id === item.id,
      )?.questions,
    },
  }));
  detail.innerHTML = comparisonView(items);
  dialog.showModal();
}

function locate() {
  if (state.busy) return;
  if (!navigator.geolocation)
    return toast("浏览器不支持定位，请输入出发商圈。");
  toast("请在浏览器中选择是否允许定位。");
  navigator.geolocation.getCurrentPosition(
    (position) => {
      sendMessage("使用我提供的当前位置", {
        name: "我的位置",
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
    },
    () => toast("未获取到位置，可以直接输入商圈或行政区。"),
    { timeout: 10000, maximumAge: 60000 },
  );
}

// One delegated action handler keeps dynamic cards and dialogs consistent.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  try {
    if (button.dataset.page) return navigate(button.dataset.page);
    if (button.hasAttribute("data-close")) return dialog.close();
    if (button.hasAttribute("data-reset")) {
      state.result = null;
      state.history = [];
      state.seen.clear();
      state.selected = null;
      return navigate("decision");
    }
    if (button.hasAttribute("data-location")) return locate();
    if (button.dataset.message)
      return await sendMessage(button.dataset.message);
    if (button.dataset.detail) {
      detail.innerHTML = detailsView(
        await merchantById(Number(button.dataset.detail)),
      );
      return dialog.showModal();
    }
    if (button.dataset.choose)
      return await choose(Number(button.dataset.choose));
    if (button.dataset.save)
      return await toggleSave(Number(button.dataset.save));
    if (button.dataset.compare)
      return await toggleCompare(Number(button.dataset.compare));
    if (button.dataset.keep) {
      const item = state.result.items.find(
        (item) => item.id === Number(button.dataset.keep),
      );
      item.kept = !item.kept;
      return renderDecision();
    }
    if (button.hasAttribute("data-open-compare")) return await openComparison();
    if (button.hasAttribute("data-clear-compare")) {
      state.compared.clear();
      return navigate(state.page);
    }
    if (button.dataset.directoryPage != null) {
      state.directoryPage = Number(button.dataset.directoryPage);
      return navigate("directory");
    }
    if (button.hasAttribute("data-show-map")) {
      const container = document.getElementById("decision-map");
      container.hidden = false;
      const result = window.NightFindWuhanMap?.draw(
        container,
        state.result.items,
      );
      if (!result?.available)
        container.textContent =
          "地图暂不可用。选定门店后仍可打开导航，或在高德核对具体分店。";
      else if (!result.pins)
        toast("这些候选暂无可用坐标；选定后可按名称和地址在地图中查找。");
    }
    // Map popups use the real merchant action generated by wuhan_map.js.
    if (button.dataset.realMerchant) {
      detail.innerHTML = detailsView(
        await merchantById(Number(button.dataset.realMerchant)),
      );
      dialog.showModal();
    }
  } catch (error) {
    toast(error.message);
  }
});

dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});
try {
  const [response, coverage] = await Promise.all([
    request("/api/real-favorites"),
    request("/api/real-merchants/coverage"),
  ]);
  state.saved = new Set(response.items.map((item) => item.id));
  state.catalogStats = coverage;
} catch (error) {
  toast(error.message);
}
navigate("decision");
