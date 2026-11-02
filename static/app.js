/* NightFind front-end.
 * Page rendering and event handling are kept in one small, dependency-free file.
 */
(function () {
  "use strict";

  const app = document.getElementById("app");
  const dialog = document.getElementById("merchant-dialog");
  const detail = document.getElementById("merchant-detail");
  const toastNode = document.getElementById("toast");
  const compareTray = document.getElementById("compare-tray");
  const compareDialog = document.getElementById("compare-dialog");
  const compareDetail = document.getElementById("compare-detail");
  const sessionKey = "nightfind-session";
  const sessionId = getSessionId();

  let districts = [];
  let aiEnabled = false;
  let realViewMode = "list";
  let realRestaurantResults = [];
  let currentPage = "chat";
  let conversation = [];
  let conversationContext = {};
  let savedIds = new Set();
  let comparisonIds = new Map();
  let seenRecommendationIds = new Set();
  let chatBusy = false;
  let toastTimer = null;

  function getSessionId() {
    let value = localStorage.getItem(sessionKey);
    if (!value) {
      value = window.crypto && crypto.randomUUID
        ? crypto.randomUUID()
        : "nf-" + Date.now() + "-" + Math.random().toString(36).slice(2);
      localStorage.setItem(sessionKey, value);
    }
    return value;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char];
    });
  }

  async function request(path, options) {
    const config = options || {};
    const headers = Object.assign(
      { "X-Session": sessionId },
      config.body ? { "Content-Type": "application/json" } : {},
      config.headers || {}
    );
    const response = await fetch(path, {
      method: config.method || "GET",
      headers: headers,
      body: config.body ? JSON.stringify(config.body) : undefined
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "请求暂时没有完成，请稍后再试。");
    }
    return data;
  }

  function showToast(message) {
    toastNode.textContent = message;
    toastNode.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      toastNode.classList.remove("visible");
    }, 2600);
  }

  function setActivePage(page) {
    currentPage = page;
    document.querySelectorAll(".nav-link").forEach(function (button) {
      button.classList.toggle("active", button.dataset.page === page);
    });
  }

  function selectOptions(values, selected) {
    return values.map(function (value) {
      const optionValue = Array.isArray(value) ? value[0] : value;
      const label = Array.isArray(value) ? value[1] : value;
      return '<option value="' + escapeHtml(optionValue) + '"' +
        (String(optionValue) === String(selected) ? " selected" : "") + ">" +
        escapeHtml(label) + "</option>";
    }).join("");
  }

  function cuisineEmoji(cuisine) {
    const icons = {
      "烧烤": "🥢",
      "小龙虾": "🦞",
      "湖北菜": "🥣",
      "家常菜": "🍚",
      "粥粉面": "🍜"
    };
    return icons[cuisine] || "🍃";
  }

  function merchantCard(merchant, compact) {
    const tags = (merchant.tags || []).slice(0, 3).map(function (tag) {
      return '<span class="tag">' + escapeHtml(tag) + "</span>";
    }).join("");
    const score = merchant.score
      ? '<span class="match-score">匹配度 ' + merchant.score + '</span>'
      : "";
    return '<article class="merchant-card">' +
      '<div class="merchant-art art-' + escapeHtml(merchant.cuisine) + '">' +
        '<span class="dish-emoji">' + cuisineEmoji(merchant.cuisine) + "</span>" +
        '<span class="art-caption">' + escapeHtml(merchant.district || "") + "</span>" +
      "</div>" +
      '<div class="merchant-card-body">' +
        '<div class="merchant-card-heading"><h3>' + escapeHtml(merchant.name) + "</h3>" +
          '<span class="rating">★ ' + Number(merchant.rating || 0).toFixed(1) + "</span></div>" +
        '<p class="merchant-summary">' + escapeHtml(merchant.description || "这家店正在等待一段更完整的介绍。") + "</p>" +
        '<div class="merchant-facts"><span>人均 ¥' + merchant.price + "</span>" +
          "<span>等位约 " + merchant.wait + " 分钟</span>" +
          (merchant.closes ? "<span>演示营业至次日 " + (merchant.closes - 24) + ":00</span>" : "") +
        "</div>" +
        '<div class="tag-row">' + tags + score + "</div>" +
        '<div class="merchant-actions">' +
          '<button class="quiet-link" type="button" data-merchant="' + merchant.id + '">' +
            (compact ? "看看这家 →" : "了解这家店 →") +
          "</button>" +
          '<button class="soft-action ' + (savedIds.has(merchant.id) ? "is-active" : "") +
            '" type="button" data-favorite="' + merchant.id + '" aria-pressed="' + savedIds.has(merchant.id) +
            '">' + (savedIds.has(merchant.id) ? "♥ 已收藏" : "♡ 今晚清单") + "</button>" +
          '<button class="soft-action ' + (comparisonIds.has(merchant.id) ? "is-active" : "") +
            '" type="button" data-compare="' + merchant.id + '" aria-pressed="' + comparisonIds.has(merchant.id) +
            '">' + (comparisonIds.has(merchant.id) ? "✓ 已选择" : "⇄ 对比") + "</button>" +
        "</div>" +
      "</div>" +
    "</article>";
  }

  function renderChatPage() {
    setActivePage("chat");
    const modeLabel = aiEnabled ? "AI 对话已连接" : "基础建议模式";
    app.innerHTML =
      '<section class="welcome-row">' +
        '<div><span class="eyebrow">A LITTLE HELP FOR TONIGHT</span>' +
          '<h1>今晚想吃点什么？</h1>' +
          '<p class="welcome-copy">不用想得太周全，先说说你现在的心情和打算。</p></div>' +
        '<div class="welcome-doodle" aria-hidden="true"><span>🍃</span><i></i><b></b></div>' +
      "</section>" +
      '<section class="chat-layout">' +
        '<div class="chat-card">' +
          '<div class="chat-card-top"><div class="helper-avatar">寻</div>' +
            '<div><strong>夜寻小帮手</strong><small>陪你一起挑，不替你做决定</small></div>' +
            '<span class="mode-pill">' + modeLabel + '</span>' +
            '<button type="button" class="reset-chat" data-reset-chat="1">重新聊</button></div>' +
          '<div id="chat-messages" class="chat-messages">' +
            '<div class="message assistant"><div class="message-avatar">寻</div>' +
              '<div class="message-content"><p>晚上好呀。你今天想吃点热乎的，还是想和朋友慢慢坐一会儿？</p>' +
              '<p>告诉我大概在哪、预算多少，或者只说一句“想吃点清淡的”也可以。</p></div></div>' +
          "</div>" +
          '<div id="context-row" class="context-row" aria-live="polite"></div>' +
          '<div class="chat-suggestions">' +
            '<button type="button" data-prompt="人均 50 元左右，想吃点清淡的">🥬 想吃清淡一点</button>' +
            '<button type="button" data-prompt="江汉路附近，朋友聚会，人均 100 元以内">🧑‍🤝‍🧑 和朋友聚餐</button>' +
            '<button type="button" data-prompt="晚上 11 点还有什么夜宵选择？">🌙 找点夜宵</button>' +
          "</div>" +
          '<form id="chat-form" class="chat-composer">' +
            '<input name="message" maxlength="2000" autocomplete="off" placeholder="说说你今晚的安排…" required>' +
            '<button type="submit" aria-label="发送消息">发送 <span>↗</span></button>' +
          "</form>" +
          '<p class="privacy-note">请勿输入姓名、电话等个人信息。配置 AI 后，对话内容会发送至所配置的模型服务。当前商户资料为演示数据。</p>' +
        "</div>" +
        '<aside class="chat-aside">' +
          '<div class="aside-note"><span class="note-icon">☀</span><h3>可以从这些开始</h3>' +
            '<p>位置、预算、时间、口味，想到哪说到哪。</p></div>' +
          '<div class="aside-tip"><span>01</span><div><b>说个大概位置</b><p>比如江汉路、光谷，或你常去的片区。</p></div></div>' +
          '<div class="aside-tip"><span>02</span><div><b>给个预算范围</b><p>人均 50 元、100 元，或者今天想省一点。</p></div></div>' +
          '<div class="aside-tip"><span>03</span><div><b>讲讲你的心情</b><p>一个人吃、朋友聚会，或散步时来点夜宵。</p></div></div>' +
          '<div class="small-note">' +
            (aiEnabled
              ? "已配置 AI 服务。推荐仍以商家数据库中的信息为准。"
              : "现在可以使用基础智能推荐。配置服务端 AI 密钥后，可启用更自然的 AI 对话。") +
          "</div>" +
        "</aside>" +
      "</section>";

    document.getElementById("chat-form").addEventListener("submit", submitChat);
    document.querySelectorAll("[data-prompt]").forEach(function (button) {
      button.addEventListener("click", function () {
        const input = document.querySelector('#chat-form input[name="message"]');
        input.value = button.dataset.prompt;
        document.getElementById("chat-form").requestSubmit();
      });
    });

    // Keep the conversation when the visitor switches to another section.
    conversation.forEach(function (entry) {
      appendMessage(entry.role, entry.content, entry.extraHtml);
    });
    renderContext();
    refreshActionButtons();
  }

  function appendMessage(role, text, extraHtml) {
    const messages = document.getElementById("chat-messages");
    const bubble = document.createElement("div");
    bubble.className = "message " + (role === "user" ? "user" : "assistant");
    if (role === "user") {
      bubble.innerHTML = '<div class="message-content"><p>' + escapeHtml(text) + "</p></div>";
    } else {
      bubble.innerHTML =
        '<div class="message-avatar">寻</div><div class="message-content"><p>' +
        escapeHtml(text).replace(/\n/g, "<br>") + "</p>" +
        (extraHtml || "") + "</div>";
    }
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }

  function renderContext() {
    const row = document.getElementById("context-row");
    if (!row) return;
    const known = conversationContext.known || [];
    const values = [];
    if (known.includes("district")) values.push(conversationContext.district);
    if (known.includes("budget")) values.push("人均 ≤ ¥" + conversationContext.budget);
    if (known.includes("wait")) values.push("等位 ≤ " + conversationContext.wait + " 分钟");
    if (known.includes("cuisine")) values.push(conversationContext.cuisine);
    if (known.includes("scene")) values.push(conversationContext.scene);
    row.innerHTML = values.length
      ? '<span class="context-label">记住了：</span>' +
          values.map(function (item) {
            return '<span class="context-pill">' + escapeHtml(item) + "</span>";
          }).join("")
      : "";
  }

  function sendQuickPrompt(message) {
    if (!message) return;
    if (currentPage !== "chat") renderChatPage();
    const form = document.getElementById("chat-form");
    if (!form) return;
    form.elements.message.value = message;
    form.requestSubmit();
  }

  async function submitChat(event) {
    event.preventDefault();
    if (chatBusy) {
      showToast("这一条正在整理，稍等一下就好。");
      return;
    }
    const form = event.currentTarget;
    const input = form.elements.message;
    const message = input.value.trim();
    if (!message) return;

    const isAlternate = /换一批|再换几家|看看别的/.test(message);
    if (!isAlternate) seenRecommendationIds.clear();
    chatBusy = true;
    const sendButton = form.querySelector('button[type="submit"]');
    sendButton.disabled = true;
    input.value = "";
    appendMessage("user", message);
    const pending = appendMessage("assistant", "我看看有哪些选择…");
    pending.classList.add("thinking");

    try {
      const result = await request("/api/chat", {
        method: "POST",
        body: {
          message: message,
          context: conversationContext,
          history: conversation.slice(-8).map(function (entry) {
            return { role: entry.role, content: entry.content };
          }),
          seen_ids: Array.from(seenRecommendationIds)
        }
      });
      pending.remove();
      conversation.push({ role: "user", content: message });
      conversationContext = result.constraints || {};

      let extra = "";
      if (result.items && result.items.length) {
        extra += '<div class="chat-recommendations"><div class="recommendation-heading">' +
          "<strong>我帮你挑出的几家</strong><span>" + result.total +
          " 家符合当前条件</span></div>" +
          result.items.slice(0, 3).map(function (merchant) {
            seenRecommendationIds.add(merchant.id);
            return '<div class="chat-merchant"><div class="chat-merchant-icon">' +
              cuisineEmoji(merchant.cuisine) + "</div><div><b>" +
              escapeHtml(merchant.name) + "</b><small>人均 ¥" + merchant.price +
              " · 等位约 " + merchant.wait + " 分钟</small></div>" +
              '<div class="chat-merchant-actions">' +
                '<button type="button" data-merchant="' + merchant.id + '">看看</button>' +
                '<button type="button" data-favorite="' + merchant.id + '">♡ 留下</button>' +
                '<button type="button" data-compare="' + merchant.id + '">⇄ 对比</button>' +
              "</div></div>";
          }).join("") + "</div>";
      }
      if (result.follow_up && result.follow_up.actions) {
        extra += '<div class="followup-section"><p class="followup-question">' +
          escapeHtml(result.follow_up.question || "还想怎么挑？") + "</p>" +
          '<div class="followup-options">' +
          result.follow_up.actions.map(function (action) {
            return '<button type="button" class="followup-chip" data-quick-prompt="' +
              escapeHtml(action.message) + '">' + escapeHtml(action.label) + "</button>";
          }).join("") + "</div></div>";
      }
      if (result.tips && result.tips.length) {
        extra += '<div class="friendly-tips"><strong>顺手提醒</strong><ul>' +
          result.tips.map(function (tip) {
            return "<li>" + escapeHtml(tip) + "</li>";
          }).join("") + "</ul></div>";
      }
      extra += '<span class="answer-mode">' +
        (result.mode === "openai" ? "AI 帮你整理" : "按现有资料整理") +
        " · 商家资料为演示数据</span>";
      conversation.push({ role: "assistant", content: result.reply, extraHtml: extra });
      if (currentPage === "chat" && document.getElementById("chat-messages")) {
        appendMessage("assistant", result.reply, extra);
        renderContext();
        refreshActionButtons();
      } else {
        showToast("新建议已经整理好了，回到「聊聊今晚」即可查看。");
      }
    } catch (error) {
      pending.remove();
      if (currentPage === "chat" && document.getElementById("chat-messages")) {
        appendMessage("assistant", error.message || "刚刚没连上，请再试一次。");
      }
    } finally {
      chatBusy = false;
      if (sendButton.isConnected) sendButton.disabled = false;
    }
  }

  async function renderMerchantPage() {
    setActivePage("merchants");
    app.innerHTML =
      '<section class="page-intro"><span class="eyebrow">THE LITTLE MERCHANT BOOK</span>' +
        '<h1>附近的好店，慢慢认识。</h1>' +
        '<p>先看看有什么，再挑一家合今晚胃口的。</p></section>' +
      '<form id="merchant-search" class="merchant-search">' +
        '<label class="search-field"><span>⌕</span><input name="keyword" placeholder="搜店名、菜系或特色"></label>' +
        '<select name="district" aria-label="选择商圈"><option value="">全部商圈</option>' +
          selectOptions(districts.map(function (item) { return [item.name, item.name]; }), "") +
        "</select>" +
        '<select name="cuisine" aria-label="选择菜系"><option value="">全部口味</option>' +
          selectOptions(["烧烤", "小龙虾", "湖北菜", "家常菜", "粥粉面"], "") +
        "</select>" +
        '<select name="max_price" aria-label="人均预算"><option value="">不限预算</option>' +
          selectOptions([[30, "人均 30 元内"], [50, "人均 50 元内"], [80, "人均 80 元内"], [100, "人均 100 元内"], [150, "人均 150 元内"]], "") +
        "</select>" +
        '<button class="button-primary" type="submit">找一找</button>' +
      "</form>" +
      '<div class="directory-toolbar"><span id="merchant-count">正在整理商家…</span>' +
        '<span>资料均为研究演示内容</span></div>' +
      '<div id="merchant-grid" class="merchant-grid"></div>';

    document.getElementById("merchant-search").addEventListener("submit", function (event) {
      event.preventDefault();
      loadMerchants(new FormData(event.currentTarget));
    });
    await loadMerchants(new FormData(document.getElementById("merchant-search")));
  }

  async function loadMerchants(formData) {
    const params = new URLSearchParams();
    ["keyword", "district", "cuisine", "max_price"].forEach(function (key) {
      const value = formData.get(key);
      if (value) params.set(key, value);
    });
    const grid = document.getElementById("merchant-grid");
    grid.innerHTML = '<div class="empty-state">正在翻翻商家小册…</div>';
    try {
      const result = await request("/api/merchants?" + params.toString());
      document.getElementById("merchant-count").textContent =
        "找到 " + result.total + " 家店";
      grid.innerHTML = result.items.length
        ? result.items.map(function (merchant) {
            return merchantCard(merchant, false);
          }).join("")
        : '<div class="empty-state">暂时没有符合条件的店。试试换个口味或放宽预算？</div>';
    } catch (error) {
      grid.innerHTML = '<div class="empty-state">' + escapeHtml(error.message) + "</div>";
    }
  }

  function realRestaurantCard(restaurant) {
    const statusLabels = {
      unknown: "营业状态待确认",
      open: "来源记录：营业",
      closed: "来源记录：已停业",
      temporarily_closed: "来源记录：暂停营业"
    };
    const price = restaurant.price_per_person == null
      ? "人均待核实"
      : "人均约 ¥" + restaurant.price_per_person;
    const area = restaurant.business_area
      ? " · " + escapeHtml(restaurant.business_area)
      : "";
    const checked = restaurant.verified_at
      ? "最近核验 " + escapeHtml(restaurant.verified_at.slice(0, 10))
      : "核验日期未记录";
    return '<article class="real-restaurant-card">' +
      (restaurant.photo_url
        ? '<img class="real-card-photo" loading="lazy" decoding="async" alt="' +
          escapeHtml(restaurant.name) + '的授权店面照片" src="' +
          escapeHtml(restaurant.photo_url) + '">'
        : '<div class="real-card-photo-placeholder" aria-label="暂无经审核的门店照片">📷 门店照片待核验</div>') +
      '<div class="real-card-top"><span class="real-verified">✓ 已核验</span>' +
        '<span class="real-status">' + escapeHtml(statusLabels[restaurant.business_status] || statusLabels.unknown) + "</span></div>" +
      '<h3>' + escapeHtml(restaurant.name) + "</h3>" +
      (restaurant.branch_name ? '<p class="real-branch">' + escapeHtml(restaurant.branch_name) + "</p>" : "") +
      '<p class="real-address">' + escapeHtml(restaurant.district) + area +
        " · " + escapeHtml(restaurant.address) + "</p>" +
      '<div class="real-facts"><span>' + escapeHtml(restaurant.cuisine || "菜系待补充") +
        "</span><b>" + price + "</b></div>" +
      '<div class="real-source"><span>' + escapeHtml(restaurant.source_name) +
        " · " + checked + "</span>" +
        '<button type="button" class="quiet-link" data-real-merchant="' +
          restaurant.id + '">查看资料 →</button></div>' +
    "</article>";
  }

  async function renderRealRestaurantsPage() {
    setActivePage("real-restaurants");
    app.innerHTML =
      '<section class="page-intro"><span class="eyebrow">WUHAN VERIFIED RESTAURANTS</span>' +
        '<h1>武汉真实餐厅，慢慢核实。</h1>' +
        '<p>这里只展示来源许可有效、并经过人工核验的真实门店。演示商户不会混进来。</p></section>' +
      '<div id="real-catalog-summary" class="real-catalog-summary">正在读取全市资料覆盖情况…</div>' +
      '<form id="real-restaurant-search" class="merchant-search">' +
        '<label class="search-field"><span>⌕</span><input name="keyword" placeholder="搜店名、菜系或地址"></label>' +
        '<select name="district" aria-label="选择行政区"><option value="">武汉全市</option></select>' +
        '<input name="cuisine" aria-label="菜系" placeholder="菜系（选填）">' +
        '<select name="max_price" aria-label="人均预算"><option value="">不限预算</option>' +
          selectOptions([[30, "人均 30 元内"], [50, "人均 50 元内"], [80, "人均 80 元内"], [100, "人均 100 元内"], [150, "人均 150 元内"], [300, "人均 300 元内"]], "") +
        "</select>" +
        '<button class="button-primary" type="submit">查找真实餐厅</button>' +
      "</form>" +
      '<div class="directory-toolbar"><span id="real-restaurant-count">正在读取已核验资料…</span>' +
        '<div class="real-view-switch" role="group" aria-label="查看方式">' +
          '<button type="button" class="soft-action is-active" data-real-view="list" aria-pressed="true">☷ 列表</button>' +
          '<button type="button" class="soft-action" data-real-view="map" aria-pressed="false">⌖ 地图</button>' +
        "</div></div>" +
      '<div id="real-restaurant-grid" class="real-restaurant-grid"></div>' +
      '<section id="real-map-panel" class="real-map-panel" hidden>' +
        '<div class="real-map-top"><strong>武汉真实餐厅分布</strong>' +
          '<span id="real-map-count">仅显示已核验、有经纬度的门店</span></div>' +
        '<div id="real-map" class="real-map" role="region" aria-label="武汉真实餐厅地图"></div>' +
        '<p>点击地图标记可以查看门店信息。地图只使用有来源、已核验的坐标；不对缺失位置进行猜测。</p>' +
      "</section>" +
      '<p class="real-data-footnote">仅展示最近两年内有来源更新记录并经人工核验的餐厅。营业状态、价格、照片和时间可能变化，请到店前再次确认。</p>';

    try {
      const [areaResult, summary] = await Promise.all([
        request("/api/real-areas"),
        request("/api/real-catalog/summary")
      ]);
      const districtsOnly = (areaResult.items || []).filter(function (area) {
        return area.area_type === "administrative_district";
      });
      const select = document.querySelector('#real-restaurant-search select[name="district"]');
      select.innerHTML = '<option value="">武汉全市</option>' +
        selectOptions(districtsOnly.map(function (area) {
          return [area.name, area.name];
        }), "");
      const coverage = (summary.districts || []).map(function (item) {
        return '<span class="coverage-item">' + escapeHtml(item.district) +
          ' <b>' + item.verified_count + "</b></span>";
      }).join("");
      document.getElementById("real-catalog-summary").innerHTML =
        '<div class="coverage-heading"><b>武汉全市资料覆盖</b><span>已核验真实门店 ' +
          summary.total_verified + " 家</span></div>" +
        '<div class="coverage-grid">' + coverage + "</div>" +
        '<p>' + escapeHtml(summary.notice) + "</p>";
      document.getElementById("real-restaurant-search").addEventListener("submit", function (event) {
        event.preventDefault();
        loadRealRestaurants(new FormData(event.currentTarget));
      });
      await loadRealRestaurants(new FormData(document.getElementById("real-restaurant-search")));
    } catch (error) {
      document.getElementById("real-restaurant-grid").innerHTML =
        '<div class="empty-state">' + escapeHtml(error.message) + "</div>";
    }
  }

  async function loadRealRestaurants(formData) {
    const params = new URLSearchParams();
    ["keyword", "district", "cuisine", "max_price"].forEach(function (key) {
      const value = String(formData.get(key) || "").trim();
      if (value) params.set(key, value);
    });
    const grid = document.getElementById("real-restaurant-grid");
    if (!grid) return;
    grid.innerHTML = '<div class="empty-state">正在查找已核验的真实餐厅…</div>';
    try {
      const result = await request("/api/real-restaurants?" + params.toString());
      realRestaurantResults = result.items || [];
      const count = document.getElementById("real-restaurant-count");
      if (count) count.textContent = "找到 " + result.total + " 家已核验餐厅";
      grid.innerHTML = result.items.length
        ? result.items.map(realRestaurantCard).join("")
        : '<div class="real-empty-state"><span>🌱</span><h2>真实餐厅名录正在建立中</h2>' +
          '<p>目前还没有符合条件、资料在两年内且完成来源许可和人工核验的门店。</p>' +
          '<p>演示商家不会显示在这里。资料入库并审核通过后，会自动出现在本页。</p></div>';
      setRealViewMode(realViewMode);
    } catch (error) {
      grid.innerHTML = '<div class="empty-state">' + escapeHtml(error.message) + "</div>";
    }
  }

  function setRealViewMode(view) {
    realViewMode = view === "map" ? "map" : "list";
    const panel = document.getElementById("real-map-panel");
    const list = document.getElementById("real-restaurant-grid");
    if (!panel || !list) return;
    const showingMap = realViewMode === "map";
    panel.hidden = !showingMap;
    list.hidden = showingMap;
    document.querySelectorAll("[data-real-view]").forEach(function (button) {
      const selected = button.dataset.realView === realViewMode;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    if (!showingMap) return;
    const message = document.getElementById("real-map-count");
    if (!window.NightFindWuhanMap) {
      message.textContent = "地图功能暂时未加载，可以使用列表查看资料。";
      return;
    }
    const result = window.NightFindWuhanMap.draw(
      document.getElementById("real-map"), realRestaurantResults
    );
    message.textContent = result.available
      ? "地图展示 " + result.pins + " 个有已核验坐标的门店"
      : "地图暂不可用，可切换回列表";
  }

  async function showRealRestaurant(restaurantId) {
    try {
      const restaurant = await request("/api/real-restaurants/" + restaurantId);
      const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
      const hours = (restaurant.hours || []).map(function (item) {
        const text = item.is_closed
          ? "休息"
          : (item.opens_at || "时间待补") + "–" + (item.closes_at || "时间待补");
        return '<div class="real-detail-row"><span>' + weekdays[item.weekday] +
          "</span><b>" + escapeHtml(text) + "</b></div>";
      }).join("");
      const dishes = (restaurant.dishes || []).map(function (dish) {
        return '<div class="real-detail-row"><span>' + escapeHtml(dish.name) +
          "</span><b>" + (dish.price == null ? "价格待核实" : "¥" + dish.price) + "</b></div>";
      }).join("");
      const price = restaurant.price_per_person == null
        ? "人均价格待核实"
        : "人均约 ¥" + restaurant.price_per_person;
      const photoGallery = (restaurant.photos || []).map(function (photo) {
        return '<figure class="real-photo-figure"><img loading="lazy" alt="' +
          escapeHtml(restaurant.name) + '的授权门店照片" src="' +
          escapeHtml(photo.photo_url) + '"><figcaption>拍摄：' +
          escapeHtml(photo.captured_at) + ' · ' +
          escapeHtml(photo.copyright_holder) + '</figcaption></figure>';
      }).join("");
      detail.innerHTML =
        '<span class="eyebrow">VERIFIED WUHAN RESTAURANT</span>' +
        '<h2>' + escapeHtml(restaurant.name) + "</h2>" +
        (restaurant.branch_name ? '<p class="real-branch">' + escapeHtml(restaurant.branch_name) + "</p>" : "") +
        '<span class="real-verified">✓ 来源许可有效 · 近两年核验通过</span>' +
        (photoGallery ? '<div class="real-photo-gallery">' + photoGallery + '</div>' :
          '<p class="real-no-photo">📷 暂无授权且近两年拍摄的门店照片</p>') +
        '<p class="detail-description">' + escapeHtml(restaurant.description || "暂无商家介绍。") + "</p>" +
        '<div class="detail-facts"><span>' + escapeHtml(restaurant.district) + "</span>" +
          "<span>" + escapeHtml(restaurant.cuisine || "菜系待补充") + "</span>" +
          "<span>" + price + "</span></div>" +
        '<p class="detail-address">' + escapeHtml(restaurant.address) + "</p>" +
        (restaurant.phone ? '<p class="detail-address">联系电话：' + escapeHtml(restaurant.phone) + "</p>" : "") +
        (restaurant.website ? '<p><a class="quiet-link" href="' + escapeHtml(restaurant.website) +
          '" target="_blank" rel="noopener noreferrer">商家网站 ↗</a></p>' : "") +
        "<h3>营业时间</h3>" + (hours || '<p class="detail-description">营业时间尚未核验。</p>') +
        "<h3>已核验菜品</h3>" + (dishes || '<p class="detail-description">暂时没有已核验的菜单资料。</p>') +
        '<p class="real-source-note">资料来源：' + escapeHtml(restaurant.source_name) +
          (restaurant.source_url.indexOf("merchant-submission:") === 0
            ? " · 商家授权提交凭证"
            : ' · <a href="' + escapeHtml(restaurant.source_url) +
              '" target="_blank" rel="noopener noreferrer">查看来源凭证 ↗</a>') + "</p>" +
        '<p class="real-source-note">来源资料更新：' +
          escapeHtml(restaurant.source_updated_at || "日期未记录") +
          ' · 最近人工核验：' + escapeHtml(restaurant.verified_at || "日期未记录") +
          "。营业状态并非实时信息，请到店前再次确认。</p>";
      dialog.showModal();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function showMerchant(merchantId) {
    try {
      const merchant = await request("/api/merchants/" + merchantId);
      const dishes = (merchant.dishes || []).map(function (dish) {
        return '<div class="dish-row"><span>' + escapeHtml(dish.name) +
          "</span><b>¥" + dish.price + "</b></div>";
      }).join("");
      const reviews = (merchant.reviews || []).map(function (review) {
        return '<div class="detail-review"><span>★ ' + review.rating +
          "</span><p>" + escapeHtml(review.comment || "没有填写文字评价") + "</p></div>";
      }).join("");
      detail.innerHTML =
        '<span class="eyebrow">A PLACE TO TRY</span><h2>' + escapeHtml(merchant.name) + "</h2>" +
        '<div class="detail-art art-' + escapeHtml(merchant.cuisine) + '">' +
          '<span class="dish-emoji">' + cuisineEmoji(merchant.cuisine) + "</span></div>" +
        '<p class="detail-description">' + escapeHtml(merchant.description) + "</p>" +
        '<div class="detail-facts"><span>' + escapeHtml(merchant.district) + "</span>" +
          "<span>" + escapeHtml(merchant.cuisine) + "</span><span>人均 ¥" + merchant.price +
          "</span><span>等位约 " + merchant.wait + " 分钟</span></div>" +
        '<p class="detail-address">' + escapeHtml(merchant.address_label || "商圈信息待补充") +
          " · 基础评分为演示值</p>" +
        '<div class="merchant-actions">' +
          '<button class="soft-action" type="button" data-favorite="' + merchant.id + '">♡ 今晚清单</button>' +
          '<button class="soft-action" type="button" data-compare="' + merchant.id + '">⇄ 加入对比</button>' +
        "</div>" +
        "<h3>菜单小记</h3>" + (dishes || '<p class="detail-description">暂时还没有菜单信息。</p>') +
        "<h3>大家的反馈</h3>" + (reviews || '<p class="detail-description">还没有收到评价。</p>') +
        '<form id="merchant-feedback" class="detail-feedback">' +
          "<h3>写下你的体验</h3><input type=\"hidden\" name=\"merchant_id\" value=\"" + merchant.id + '">' +
          '<label>给这家店打个分<select name="rating">' +
            selectOptions([[5, "5 分 · 很喜欢"], [4, "4 分 · 不错"], [3, "3 分 · 还可以"], [2, "2 分 · 有待改进"], [1, "1 分 · 不太满意"]], 5) +
          "</select></label>" +
          '<textarea name="comment" maxlength="2000" placeholder="分享一点真实体验（选填）"></textarea>' +
          '<button class="button-primary" type="submit">提交反馈</button></form>' +
        '<p class="data-note">提示：商家介绍、菜品、价格和基础评分是演示资料，地址为示例商圈标签，不是实际门牌。</p>';
      dialog.showModal();
      document.getElementById("merchant-feedback").addEventListener("submit", submitMerchantFeedback);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function submitMerchantFeedback(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    try {
      await request("/api/feedback", {
        method: "POST",
        body: {
          merchant_id: Number(values.merchant_id),
          rating: Number(values.rating),
          comment: values.comment
        }
      });
      showToast("谢谢你，反馈已经收到。");
      dialog.close();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function renderSuggestionsPage() {
    setActivePage("suggestions");
    let summary = { total: 0, categories: [] };
    try {
      summary = await request("/api/suggestions/summary");
    } catch (error) {
      // The form remains available if the optional summary request fails.
    }
    app.innerHTML =
      '<section class="page-intro"><span class="eyebrow">A NOTE FROM YOU</span>' +
        '<h1>有想法，就告诉我们。</h1>' +
        '<p>一条小建议，也许就能让下一次选择变得更顺手。</p></section>' +
      '<section class="suggestion-layout">' +
        '<form id="suggestion-form" class="suggestion-form">' +
          '<div class="form-heading"><span class="form-flower">✿</span><div><h2>写下你的想法</h2>' +
            '<p>不用正式，想到什么就写什么。</p></div></div>' +
          '<label>这条建议属于哪一类？<select name="category">' +
            selectOptions(["功能建议", "商家信息", "使用体验", "其他"], "功能建议") +
          "</select></label>" +
          '<label>你想告诉我们什么？<textarea name="message" rows="7" maxlength="2000" required placeholder="比如：希望可以按营业时间筛选，或者补充素食选项…"></textarea></label>' +
          '<div class="form-bottom"><span>请不要填写密码、电话等敏感个人信息。</span>' +
            '<button class="button-primary" type="submit">提交建议 <span>↗</span></button></div>' +
        "</form>" +
        '<aside class="suggestion-aside"><div class="note-illustration">🌱</div>' +
          '<h3>让夜寻慢慢长好</h3><p>我们会把大家的建议作为产品改进参考。当前是研究原型，暂不提供公开回复或处理进度。</p>' +
          '<div class="suggestion-count"><strong>' + summary.total + "</strong><span>条建议已收到</span></div>" +
          (summary.categories || []).map(function (item) {
            return '<div class="category-count"><span>' + escapeHtml(item.category) +
              '</span><b>' + item.count + "</b></div>";
          }).join("") +
        "</aside></section>";
    document.getElementById("suggestion-form").addEventListener("submit", submitSuggestion);
  }

  async function submitSuggestion(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form));
      await request("/api/suggestions", {
        method: "POST",
        body: values
      });
      showToast("收到啦，谢谢你愿意帮夜寻变得更好。");
      await renderSuggestionsPage();
    } catch (error) {
      showToast(error.message);
      button.disabled = false;
    }
  }

  /* Tonight List: saved items belong to the browser's visitor session. */
  function refreshActionButtons() {
    const savedCount = document.getElementById("saved-count");
    if (savedCount) savedCount.textContent = savedIds.size;
    document.querySelectorAll("[data-favorite]").forEach(function (button) {
      const isSaved = savedIds.has(Number(button.dataset.favorite));
      button.classList.toggle("is-active", isSaved);
      button.setAttribute("aria-pressed", String(isSaved));
      if (button.closest(".chat-merchant-actions")) {
        button.textContent = isSaved ? "♥ 已留" : "♡ 留下";
      } else {
        button.textContent = isSaved ? "♥ 已收藏" : "♡ 今晚清单";
      }
    });
    document.querySelectorAll("[data-compare]").forEach(function (button) {
      const selected = comparisonIds.has(Number(button.dataset.compare));
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", String(selected));
      button.textContent = selected ? "✓ 已选" : "⇄ 对比";
    });
    renderCompareTray();
  }

  async function toggleFavorite(merchantId) {
    const active = !savedIds.has(merchantId);
    try {
      await request("/api/favorites", {
        method: "POST",
        body: { merchant_id: merchantId, active: active }
      });
      if (active) savedIds.add(merchantId);
      else savedIds.delete(merchantId);
      showToast(active ? "已经放进今晚清单啦。" : "已从今晚清单移除。");
      if (currentPage === "saved") await renderSavedPage();
      refreshActionButtons();
    } catch (error) {
      showToast(error.message);
    }
  }

  /* Compare selection remains in memory until the visitor clears it. */
  async function toggleComparison(merchantId) {
    if (comparisonIds.has(merchantId)) {
      comparisonIds.delete(merchantId);
      refreshActionButtons();
      return;
    }
    if (comparisonIds.size >= 3) {
      showToast("一次最多对比三家，先移除一家再选吧。");
      return;
    }
    try {
      const merchant = await request("/api/merchants/" + merchantId);
      comparisonIds.set(merchantId, merchant.name);
      refreshActionButtons();
      if (comparisonIds.size === 2) {
        showToast("已选两家，可以开始对比啦。");
      }
    } catch (error) {
      showToast(error.message);
    }
  }

  function renderCompareTray() {
    if (!compareTray) return;
    if (!comparisonIds.size) {
      compareTray.hidden = true;
      compareTray.innerHTML = "";
      return;
    }
    compareTray.hidden = false;
    const names = Array.from(comparisonIds.values()).map(escapeHtml).join("、");
    compareTray.innerHTML =
      '<div class="compare-tray-summary"><b>已选 ' + comparisonIds.size +
      ' / 3 家</b><small>' + names + "</small></div>" +
      '<button type="button" class="soft-action" data-clear-compare="1">清空</button>' +
      '<button type="button" class="button-primary" data-open-compare="1"' +
        (comparisonIds.size < 2 ? " disabled" : "") + '>一起比较 →</button>';
  }

  async function showComparison() {
    const ids = Array.from(comparisonIds.keys());
    if (ids.length < 2 || ids.length > 3) {
      showToast("请先选择两到三家餐厅。");
      return;
    }
    try {
      const params = new URLSearchParams({ ids: ids.join(",") });
      const known = conversationContext.known || [];
      if (known.includes("scene")) params.set("scene", conversationContext.scene);
      const result = await request("/api/compare?" + params.toString());
      const winner = result.summary.recommended_id;
      const cols = result.items.map(function (merchant) {
        const isTop = merchant.id === winner;
        const highlights = merchant.highlights.map(function (label) {
          return "<span>" + escapeHtml(label) + "</span>";
        }).join("");
        return '<article class="compare-column ' + (isTop ? "top" : "") + '">' +
          '<div class="dish-emoji" aria-hidden="true">' +
            cuisineEmoji(merchant.cuisine) + "</div>" +
          '<h3>' + escapeHtml(merchant.name) + "</h3>" +
          '<div class="compare-metric"><span>人均</span><b>¥' + merchant.price + "</b></div>" +
          '<div class="compare-metric"><span>预计等位</span><b>' + merchant.wait + " 分钟</b></div>" +
          '<div class="compare-metric"><span>菜系</span><b>' + escapeHtml(merchant.cuisine) + "</b></div>" +
          '<div class="compare-metric"><span>商圈</span><b>' + escapeHtml(merchant.district) + "</b></div>" +
          '<div class="compare-metric"><span>演示评分</span><b>★ ' +
            Number(merchant.rating).toFixed(1) + "</b></div>" +
          '<div class="compare-tags">' + highlights + "</div>" +
          '<div class="merchant-actions">' +
            '<button class="soft-action" type="button" data-favorite="' +
              merchant.id + '">♡ 今晚清单</button>' +
          "</div>" +
        "</article>";
      }).join("");
      compareDetail.innerHTML =
        '<span class="eyebrow">CHOOSE WHAT MATTERS TO YOU</span>' +
        '<h2>这几家，怎么选？</h2>' +
        '<p class="compare-intro">按照人均、等位和口味，把优缺点放在一起看。</p>' +
        '<div class="compare-columns ' + (result.items.length === 2 ? "two" : "") +
          '">' + cols + "</div>" +
        '<div class="compare-conclusion"><strong>夜寻的比较建议</strong><p>' +
          escapeHtml(result.summary.reason) + "</p><ul>" +
          result.summary.details.map(function (text) {
            return "<li>" + escapeHtml(text) + "</li>";
          }).join("") + "</ul></div>" +
        '<p class="compare-disclaimer">' +
          escapeHtml(result.summary.sample_notice) + "</p>";
      compareDialog.showModal();
      refreshActionButtons();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function renderSavedPage() {
    setActivePage("saved");
    app.innerHTML =
      '<section class="page-intro"><span class="eyebrow">YOUR LITTLE DINNER LIST</span>' +
        '<h1>把心动的店，留给今晚。</h1>' +
        '<p>收藏会留在当前浏览器的访客会话中，换设备不会自动同步。</p></section>' +
      '<div class="saved-hero"><div><strong>今晚不必一下子决定</strong>' +
        '<p>先记下喜欢的几家，再挑两三家放到一起比较。</p></div>' +
        '<span class="saved-illustration" aria-hidden="true">🌿</span></div>' +
      '<div id="saved-content"><div class="empty-state">正在翻翻今晚的清单…</div></div>';

    try {
      const result = await request("/api/saved");
      if (currentPage !== "saved") return;
      const merchants = result.items || [];
      savedIds = new Set(merchants.map(function (item) { return item.id; }));
      const content = document.getElementById("saved-content");
      if (merchants.length) {
        content.innerHTML = '<div class="directory-toolbar"><span>记下了 ' +
          merchants.length + ' 家店</span><span>可以收藏、查看或加入对比</span></div>' +
          '<div class="saved-grid">' +
          merchants.map(function (merchant) {
            return merchantCard(merchant, true);
          }).join("") + '</div>' +
          '<div class="saved-actions"><button type="button" class="button-primary" ' +
            'data-page="merchants">再逛逛商家小册 →</button></div>';
      } else {
        content.innerHTML =
          '<div class="saved-empty"><span class="empty-icon">🍵</span>' +
            '<h2>今晚的清单还是空的</h2>' +
            '<p>看到喜欢的店，点一下“今晚清单”就能留在这里。</p>' +
            '<button class="button-primary" type="button" data-page="merchants">去看看有什么好吃的 →</button>' +
          "</div>";
      }
      refreshActionButtons();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function navigate(page) {
    if (currentPage === "real-restaurants" && page !== "real-restaurants" &&
        window.NightFindWuhanMap) {
      window.NightFindWuhanMap.dispose();
    }
    if (page === "chat") {
      renderChatPage();
    } else if (page === "merchants") {
      await renderMerchantPage();
    } else if (page === "real-restaurants") {
      await renderRealRestaurantsPage();
    } else if (page === "suggestions") {
      await renderSuggestionsPage();
    } else if (page === "saved") {
      await renderSavedPage();
    }
    refreshActionButtons();
  }

  document.addEventListener("click", function (event) {
    const pageButton = event.target.closest("[data-page]");
    if (pageButton) {
      navigate(pageButton.dataset.page);
      return;
    }
    const quickButton = event.target.closest("[data-quick-prompt]");
    if (quickButton) {
      sendQuickPrompt(quickButton.dataset.quickPrompt);
      return;
    }
    if (event.target.closest("[data-reset-chat]")) {
      conversation = [];
      conversationContext = {};
      seenRecommendationIds.clear();
      renderChatPage();
      showToast("从头聊聊，今晚重新挑。");
      return;
    }
    const favoriteButton = event.target.closest("[data-favorite]");
    if (favoriteButton) {
      toggleFavorite(Number(favoriteButton.dataset.favorite));
      return;
    }
    const compareButton = event.target.closest("[data-compare]");
    if (compareButton) {
      toggleComparison(Number(compareButton.dataset.compare));
      return;
    }
    if (event.target.closest("[data-open-compare]")) {
      showComparison();
      return;
    }
    if (event.target.closest("[data-clear-compare]")) {
      comparisonIds.clear();
      refreshActionButtons();
      return;
    }
    const realViewButton = event.target.closest("[data-real-view]");
    if (realViewButton) {
      setRealViewMode(realViewButton.dataset.realView);
      return;
    }
    const realMerchantButton = event.target.closest("[data-real-merchant]");
    if (realMerchantButton) {
      showRealRestaurant(Number(realMerchantButton.dataset.realMerchant));
      return;
    }
    const merchantButton = event.target.closest("[data-merchant]");
    if (merchantButton) {
      showMerchant(Number(merchantButton.dataset.merchant));
    }
  });

  document.querySelector(".dialog-close").addEventListener("click", function () {
    dialog.close();
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });

  document.querySelector(".compare-close").addEventListener("click", function () {
    compareDialog.close();
  });
  compareDialog.addEventListener("click", function (event) {
    if (event.target === compareDialog) compareDialog.close();
  });

  async function start() {
    try {
      const bootstrap = await request("/api/bootstrap");
      districts = bootstrap.districts || [];
      aiEnabled = Boolean(bootstrap.ai_enabled);
      savedIds = new Set(bootstrap.favorites || []);
      renderChatPage();
      refreshActionButtons();
    } catch (error) {
      app.innerHTML = '<div class="empty-state">暂时连接不上夜寻服务。请确认终端里的服务仍在运行，然后刷新页面。</div>';
      showToast(error.message);
    }
  }

  start();
})();
