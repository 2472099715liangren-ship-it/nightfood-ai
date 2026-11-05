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
  focusMerchant: null,
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
  if (!stats) return '<p class="source-note">正在读取武汉商家资料…</p>';
  return `<div class="catalog-summary" data-catalog-count="${stats.public_total}">
    <span><strong>${stats.public_total}</strong> 家真实来源商家</span>
    <span><strong>${stats.mapped_total}</strong> 个地图点位</span>
    <details><summary>资料覆盖说明 ↗</summary><p>近五年来源资料。已收录 ${stats.priced_merchant_total} 家门店的 ${stats.priced_menu_items} 条菜品单价，其中 ${stats.priced_mapped_total} 家有坐标。未收录的价格、电话和营业时间会在资料卡中注明；记录不代表实时营业。</p></details></div>`;
}

function renderDecision() {
  window.NightFindWuhanMap?.dispose();
  const result = state.result;
  const mode = result?.mode === "ai" ? "AI 理解" : "本地解析";
  const greeting = [
    {
      role: "assistant",
      text: "你好，我是夜寻。\n今天想吃点什么？告诉我人数、预算和位置，一起挑一家合适的店。也可以直接查店名、菜单和价格。",
    },
  ];
  root.innerHTML = `<section class="page-intro decision-intro"><div><span class="eyebrow">WUHAN · A LITTLE TASTE OF THE NIGHT</span>
    <h1>把今晚，交给一顿<span>好饭。</span></h1><p>聊聊想吃什么，让选择简单一点。<br>从武汉真实商家里，找到合你心意的那一家。</p></div>
    <div class="hero-art" aria-hidden="true"><svg viewBox="0 0 220 150" fill="none"><ellipse cx="111" cy="132" rx="77" ry="8" fill="#dce7d3"/><path d="M38 74h145c-4 38-30 56-72 56S43 112 38 74Z" fill="#e1ebd5" stroke="#779773" stroke-width="2"/><ellipse cx="111" cy="74" rx="73" ry="17" fill="#fafbf3" stroke="#779773" stroke-width="2"/><path d="M60 76c25-21 60-20 99-2M62 82c34-23 63-21 96-2M75 85c20-14 48-18 73-3" stroke="#b8ba83" stroke-width="3"/><path d="M127 62 167 17m-29 47 43-43" stroke="#7e8966" stroke-width="4" stroke-linecap="round"/><path d="M86 43c-13-13 11-15 1-29m23 35c-10-12 10-16 3-29" stroke="#a4b79a" stroke-width="2" stroke-linecap="round"/><path d="M47 61C24 57 19 43 21 32c20 1 31 11 26 29Z" fill="#ccddba"/><path d="m27 39 21 24" stroke="#8daa7d"/></svg><span>好好吃饭 · 慢慢选择</span></div></section>
    <div class="decision-workspace"><section class="decision-input" aria-label="AI 对话区域">
      <header class="chat-heading"><span class="helper-avatar" aria-hidden="true">夜</span><div><h2>和夜寻聊聊</h2><p>你的武汉餐饮小向导</p></div><span class="mode-pill">${mode} · 真实资料库</span></header>
      <div id="conversation-log" class="chat-messages" role="log" aria-label="与夜寻的对话" aria-live="polite">${(state
        .history.length
        ? state.history
        : greeting
      )
        .slice(-10)
        .map(
          (entry) =>
            `<div class="message ${entry.role === "user" ? "user" : "assistant"}">${entry.role === "user" ? "" : '<span class="message-avatar" aria-hidden="true">夜</span>'}<div class="message-content"><span class="sr-only">${entry.role === "user" ? "你" : "夜寻"}：</span>${e(entry.text)}</div></div>`,
        )
        .join("")}
        ${state.busy ? '<div class="thinking" role="status">夜寻正在整理你的需求 <span>···</span></div>' : ""}</div>
      <div class="quick-actions"><span>试着问问</span>${(result?.follow_up?.actions || ["武汉有哪些真实商家", "有哪些咖啡店", "查金贵源的菜单价格"]).map((message) => `<button type="button" data-message="${e(message)}" ${state.busy ? "disabled" : ""}>${e(message)} ↗</button>`).join("")}</div>
      <form id="decision-form" class="chat-composer"><label class="sr-only" for="request-message">你的用餐需求</label><textarea id="request-message" name="message" maxlength="2000" required placeholder="比如：今晚七点，四个人在江汉路附近，总共三百元，想吃湖北菜…" ${state.busy ? "disabled" : ""}></textarea>
        <div class="composer-actions"><div><button type="button" data-location ${state.busy ? "disabled" : ""}>⌖ 我的位置</button><button type="button" data-reset ${state.busy ? "disabled" : ""}>↻ 重新聊</button></div><button type="submit" class="button-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "正在寻找…" : "帮我找找 ↗"}</button></div></form>
      ${result?.mode === "fallback" ? '<p class="source-note">AI 暂不可用，已切换本地条件解析。</p>' : ""}
    </section><aside class="decision-aside"><section class="conditions" aria-label="已理解的条件"><span class="eyebrow">YOUR DINING NOTES</span><h2>今晚的用餐笔记</h2>${constraintsView(result?.constraints, result?.budget_per_person)}</section>
      <section class="journey-note"><span class="eyebrow">一顿好饭，三步就好</span><ol><li><span>01</span><div><strong>聊聊你的想法</strong><small>人数、预算、位置与口味</small></div></li><li><span>02</span><div><strong>看看适合的店</strong><small>比较菜单、价格和真实位置</small></div></li><li><span>03</span><div><strong>选好，就出发</strong><small>打开地图，或联系门店</small></div></li></ol><button type="button" data-page="directory">去武汉地图逛逛 ↗</button></section></aside></div>
    ${catalogSummary()}
    <section id="selected-place" ${state.selected ? "" : "hidden"}>${state.selected ? choiceView(state.selected) : ""}</section>
    ${
      result
        ? `<section class="candidate-section" aria-live="polite"><div class="section-heading"><div><span class="eyebrow">PICK YOUR FAVORITE</span><h2>${result.stage === "clarify" ? "再补充一点，就更合适了" : result.stage === "catalog" ? "在武汉，为你找到这些店" : "这几家，值得你看看"}</h2></div>${result.items.length ? '<button type="button" data-show-map>⌖ 在地图上比较</button>' : ""}</div>
      <p class="reply-text muted">${e(result.reply)}</p>
      ${result.items.length ? `<div class="decision-grid">${merchantCards(result.items, state.saved, state.compared, true)}</div><div id="decision-map" class="decision-map" hidden role="region" aria-label="候选餐厅地图"></div>` : ""}
      ${
        Object.keys(result.excluded).length
          ? `<details class="filter-explanation"><summary>查看其他门店的筛选原因</summary><ul>${Object.entries(
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
  const log = document.getElementById("conversation-log");
  log.scrollTop = log.scrollHeight;
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
  root.innerHTML = `<section class="page-intro"><span class="eyebrow">${state.page === "saved" ? "YOUR LITTLE COLLECTION" : "EXPLORE WUHAN"}</span><h1>${state.page === "saved" ? "心仪的店，留给今晚。" : "沿着武汉，寻一口喜欢。"}</h1><p>${state.page === "saved" ? "把喜欢的店放在一起，下一顿就有了灵感。" : "看真实位置，翻翻菜单，再决定往哪走。"}</p></section>${catalogSummary()}
    ${state.page === "directory" ? `<form id="directory-form" class="directory-search"><label>店名、菜系或地址<input name="keyword" value="${e(state.keyword)}" maxlength="80"></label><label>行政区<input name="district" value="${e(state.district)}" placeholder="例如：江汉区"></label><button class="button-primary">搜索</button></form>` : ""}
    ${state.page === "directory" ? '<section class="directory-map-section"><div class="section-heading"><div><span class="eyebrow">WUHAN FOOD MAP</span><h2>武汉寻味地图</h2></div><button type="button" data-map-all>查看全部点位 ⤢</button></div><p id="directory-map-status" class="source-note">正在加载武汉底图和商家坐标…</p><div id="directory-map" class="decision-map" role="region" aria-label="武汉真实商家地图"></div><div class="map-caption"><span><i></i> 真实来源商家 · 点击查看资料</span><span>在线街道图不可用时显示武汉离线简图 · 可拖动缩放</span></div></section><div class="section-heading"><h2>发现武汉的味道</h2><span>每家店，资料有出处</span></div>' : ""}
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
        const drawn = await window.NightFindWuhanMap?.draw(
          container,
          mapped.items,
          { overview: true },
        );
        if (version !== pageVersion) return;
        container.dataset.pins = drawn?.pins || 0;
        status.textContent = `找到 ${mapped.total} 家商家，已载入 ${drawn?.pins || 0} 个来源坐标；地图展示全部筛选点位，不受列表分页限制。`;
        if (state.focusMerchant != null) {
          window.NightFindWuhanMap?.focus(state.focusMerchant);
          state.focusMerchant = null;
        }
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

async function navigate(page) {
  state.page = page;
  pageVersion += 1;
  window.NightFindWuhanMap?.dispose();
  document
    .querySelectorAll("[data-page]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.page === page),
    );
  if (page === "decision") renderDecision();
  renderTray();
  if (page !== "decision") await renderDirectory(pageVersion);
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
    if (button.hasAttribute("data-map-all"))
      return window.NightFindWuhanMap?.fitAll();
    if (button.dataset.mapMerchant) {
      const id = Number(button.dataset.mapMerchant);
      dialog.close();
      if (window.NightFindWuhanMap?.focus(id)) return;
      state.keyword = "";
      state.district = "";
      state.directoryPage = 0;
      state.focusMerchant = id;
      return await navigate("directory");
    }
    if (button.hasAttribute("data-show-map")) {
      const container = document.getElementById("decision-map");
      container.hidden = false;
      const result = await window.NightFindWuhanMap?.draw(
        container,
        state.result.items,
      );
      if (!result?.available)
        container.textContent =
          "地图暂不可用。选定门店后仍可打开导航，或在高德核对具体分店。";
      else if (!result.pins)
        toast("这些候选暂无可用坐标；选定后可按名称和地址在地图中查找。");
      container.scrollIntoView({ behavior: "smooth", block: "center" });
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

// A blocked external image should leave the designed cover, not a broken-image icon.
document.addEventListener(
  "error",
  (event) => {
    if (!(event.target instanceof HTMLImageElement)) return;
    event.target.hidden = true;
    const caption = event.target.parentElement.querySelector(".image-caption");
    if (caption) caption.hidden = true;
    const credit = event.target
      .closest(".decision-card")
      ?.querySelector(".image-credit");
    if (credit) credit.hidden = true;
  },
  true,
);
