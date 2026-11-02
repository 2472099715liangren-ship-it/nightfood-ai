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
            '<span class="mode-pill">' + modeLabel + "</span></div>" +
          '<div id="chat-messages" class="chat-messages">' +
            '<div class="message assistant"><div class="message-avatar">寻</div>' +
              '<div class="message-content"><p>晚上好呀。你今天想吃点热乎的，还是想和朋友慢慢坐一会儿？</p>' +
              '<p>告诉我大概在哪、预算多少，或者只说一句“想吃点清淡的”也可以。</p></div></div>' +
          "</div>" +
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
      appendMessage(entry.role, entry.content);
    });
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

  async function submitChat(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.message;
    const message = input.value.trim();
    if (!message) return;

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
          history: conversation.slice(-8)
        }
      });
      pending.remove();
      conversation.push({ role: "user", content: message });
      conversation.push({ role: "assistant", content: result.reply });
      conversationContext = result.constraints || {};

      let extra = "";
      if (result.items && result.items.length) {
        extra += '<div class="chat-recommendations"><div class="recommendation-heading">' +
          "<strong>我帮你挑出的几家</strong><span>" + result.total + " 家符合条件</span></div>" +
          result.items.slice(0, 3).map(function (merchant) {
            return '<div class="chat-merchant"><div class="chat-merchant-icon">' +
              cuisineEmoji(merchant.cuisine) + "</div><div><b>" +
              escapeHtml(merchant.name) + "</b><small>人均 ¥" + merchant.price +
              " · 等位约 " + merchant.wait + " 分钟</small></div>" +
              '<button type="button" data-merchant="' + merchant.id + '">看看</button></div>';
          }).join("") + "</div>";
      }
      if (result.tips && result.tips.length) {
        extra += '<div class="friendly-tips"><strong>顺手提醒</strong><ul>' +
          result.tips.map(function (tip) {
            return "<li>" + escapeHtml(tip) + "</li>";
          }).join("") + "</ul></div>";
      }
      extra += '<span class="answer-mode">' +
        (result.mode === "openai" ? "AI 帮你整理" : "按现有资料整理") +
        "</span>";
      appendMessage("assistant", result.reply, extra);
    } catch (error) {
      pending.remove();
      appendMessage("assistant", error.message || "刚刚没连上，请再试一次。");
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

  async function navigate(page) {
    if (page === "chat") {
      renderChatPage();
    } else if (page === "merchants") {
      await renderMerchantPage();
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
