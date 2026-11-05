/* Pure HTML renderers. API calls and mutable page state belong in app.js. */
export function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
}
const e = escapeHtml;

export function externalLink(url, label, className = "") {
  try {
    if (!["https:", "http:", "tel:"].includes(new URL(url).protocol)) return "";
  } catch {
    return "";
  }
  return `<a class="${e(className)}" href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(label)}</a>`;
}

export function priceLabel(item) {
  if (item.price_range_min != null && item.price_range_max != null) {
    const basis =
      item.price_range_basis === "per_person"
        ? "参考人均"
        : item.price_range_basis === "dish"
          ? "菜品参考价"
          : "来源参考价（单位未注明）";
    return `${basis} ¥${item.price_range_min}–${item.price_range_max}`;
  }
  return item.price_per_person != null
    ? `参考人均 ¥${item.price_per_person}`
    : "人均价格暂未收录";
}

function hasCoordinates(item) {
  return item.latitude != null && item.longitude != null;
}
function districtLabel(item) {
  return !item.district || item.district.includes("待确认")
    ? "武汉"
    : item.district;
}
function dishes(item) {
  return (item.signature_dishes || "").split(/[;；]/).filter(Boolean);
}
function mapAction(item) {
  return hasCoordinates(item)
    ? `<button type="button" data-map-merchant="${item.id}">⌖ 在地图查看</button>`
    : externalLink(item.map_search_url, "↗ 按店名查地图", "button-secondary");
}

export function constraintsView(context, budgetPerPerson) {
  if (!context)
    return `<div class="needs-empty"><span class="needs-symbol" aria-hidden="true">⌁</span>
    <p>先聊聊想吃什么，<br>我会帮你理清用餐需求。</p></div>
    <div class="condition-tags"><span>几个人</span><span>花多少钱</span><span>在哪吃</span><span>什么口味</span></div>`;
  const labels = [
    context.party_size ? `${context.party_size} 人同行` : "人数待补充",
    context.budget != null
      ? `${context.budget_kind === "total" ? "总预算" : context.budget_kind === "per_person" ? "人均" : "预算单位待补充"} ¥${context.budget}`
      : "预算待补充",
    context.location?.name || "出发位置待补充",
    context.arrival
      ? `${context.arrival.slice(0, 16).replace("T", " ")}（北京时间${context.arrival_date_inferred ? "，按今天推定" : ""}）`
      : "用餐时间待补充",
    context.cuisine || "不限口味",
    context.radius_km ? `直线距离 ≤ ${context.radius_km} km` : "",
    context.avoid?.length ? `忌口：${context.avoid.join("、")}` : "",
    context.wait_minutes != null
      ? `期望等位 ≤ ${context.wait_minutes} 分钟`
      : "",
  ].filter(Boolean);
  const derived =
    context.budget_kind === "total" && budgetPerPerson != null
      ? `<p class="source-note">按 ${context.party_size} 人计算，人均预算约 ¥${budgetPerPerson.toFixed(2)}。</p>`
      : "";
  return `<div class="condition-tags">${labels.map((label) => `<span>${e(label)}</span>`).join("")}</div>${derived}
    ${context.location?.note ? `<p class="source-note">${e(context.location.note)}</p>` : ""}`;
}

function coverView(item) {
  const cuisine = item.cuisine_display || item.cuisine || "风味餐饮";
  const category = /咖啡|coffee/i.test(cuisine)
    ? "咖"
    : /茶|tea/i.test(cuisine)
      ? "茶"
      : /面|noodle/i.test(cuisine)
        ? "面"
        : "食";
  const image = item.photo_url || item.cover_image_url;
  const caption = item.photo_url
    ? "门店照片"
    : item.cover_image_type === "dish_reference"
      ? "菜品参考图 · 非分店实拍"
      : item.cover_image_type === "storefront"
        ? "来源门店图"
        : "来源菜品图";
  return `<div class="merchant-cover" aria-label="${e(cuisine)}">
    <span class="cover-letter" aria-hidden="true">${category}</span><span class="cover-caption">${e(cuisine)}</span>
    ${image ? `<img src="${e(image)}" alt="${e(item.cover_image_caption || item.name)}" loading="lazy" referrerpolicy="no-referrer"><span class="image-caption">${caption}</span>` : ""}
    <span class="cover-location">${e(districtLabel(item))}</span></div>`;
}

export function merchantCards(items, saved, compared, showKeep = false) {
  if (!items.length)
    return '<div class="empty-state"><strong>还没有找到合适的门店</strong><p>试试更换关键词，或放宽预算和距离条件。</p></div>';
  return items
    .map(
      (item, index) => `<article class="decision-card" data-card="${item.id}">
    ${coverView(item)}<div class="merchant-card-body">
    ${item.cover_image_url && !item.photo_url ? `<div class="image-credit">${e(item.cover_image_author)} · ${externalLink(item.cover_image_license_url, item.cover_image_license)} · ${externalLink(item.cover_image_source_url, "图片来源")}</div>` : ""}
    <div class="merchant-title-row"><span class="eyebrow">${showKeep ? `候选 0${index + 1}` : e(item.source_name || "真实商家")}</span>
      <button type="button" class="save-icon" data-save="${item.id}" aria-label="${saved.has(item.id) ? "取消收藏" : "收藏"}${e(item.name)}" aria-pressed="${saved.has(item.id)}">${saved.has(item.id) ? "♥" : "♡"}</button></div>
    <h2>${e(item.name)}</h2>
    <div class="merchant-meta"><span>${e(item.cuisine_display || item.cuisine || "菜系暂未收录")}</span><span>${item.distance_km != null ? `距你约 ${e(item.distance_km)} km · 直线` : hasCoordinates(item) ? "已收录地图坐标" : "可按地址查找"}</span></div>
    <p class="merchant-price">${e(priceLabel(item))}</p>
    <dl class="card-facts"><div><dt>地址</dt><dd>${e(item.address || "来源未提供门牌地址，可查看坐标位置")}</dd></div>
      <div><dt>营业</dt><dd>${e(item.opening_hours || "时间暂未收录")}</dd></div>
      <div><dt>电话</dt><dd>${item.phone_url ? externalLink(item.phone_url, item.phone) : e(item.phone || "电话暂未收录")}</dd></div></dl>
    <div class="menu-preview"><h3>招牌与菜单</h3>${
      (item.priced_menu || []).length
        ? item.priced_menu
            .map(
              (dish) =>
                `<div class="menu-preview-row"><span>${e(dish.dish_name)}</span><strong>¥${e(dish.price)}<small> ${e(dish.price_unit)}</small></strong></div>`,
            )
            .join("")
        : dishes(item).length
          ? `<p>${dishes(item).slice(0, 4).map(e).join(" / ")}</p><small>菜品单价暂未收录</small>`
          : '<p class="muted">菜单与单价暂未收录，可查看商家来源。</p>'
    }</div>
    ${item.reasons?.length ? `<div class="recommendation-reason"><span>为什么选它</span><p>${item.reasons.map(e).join("；")}</p></div>` : ""}
    ${item.estimated_total != null ? `<p class="source-note">本次来源参考价估算 ¥${e(item.estimated_total)}，以实际消费为准。</p>` : ""}
    ${item.questions?.length ? `<details class="preflight-note"><summary>出发前的小提醒 · ${item.questions.length} 项</summary><ul>${item.questions.map((text) => `<li>${e(text)}</li>`).join("")}</ul></details>` : ""}
    <div class="merchant-source">${e(item.source_name || "公开资料")} · ${item.source_checked_at ? "来源日期 " : item.source_collected_at ? "采集 " : item.source_archived_at ? "归档 " : ""}${e(item.source_checked_at || item.source_collected_at || item.source_archived_at || "日期未注明")}</div>
    <div class="card-actions card-main-actions"><button type="button" class="button-primary" data-detail="${item.id}">查看菜单与资料 ↗</button>${mapAction(item)}</div>
    <div class="card-actions card-minor-actions"><button type="button" data-compare="${item.id}" aria-pressed="${compared.has(item.id)}">${compared.has(item.id) ? "✓ 已选对比" : "+ 加入对比"}</button>
    ${showKeep ? `<button type="button" data-keep="${item.id}" aria-pressed="${!!item.kept}">${item.kept ? "✓ 已保留" : "下轮保留"}</button>` : ""}
    <button type="button" data-choose="${item.id}">就选这家 →</button></div></div></article>`,
    )
    .join("");
}

export function detailsView(item) {
  const images =
    (item.photos || [])
      .map(
        (photo) =>
          `<figure><img src="${e(photo.photo_url)}" alt="${e(item.name)}的门店照片" loading="lazy"><figcaption>拍摄 ${e(photo.taken_at)} · ${e(photo.copyright_holder)}</figcaption></figure>`,
      )
      .join("") +
    (item.images || [])
      .map(
        (image) =>
          `<figure><img src="${e(image.image_url)}" alt="${e(image.caption)}" loading="lazy"><figcaption>${image.image_type === "dish_reference" ? "菜品参考图，非该分店实拍 · " : ""}${e(image.caption)} · ${e(image.author)} · ${externalLink(image.license_url, image.license) || e(image.license)}${image.taken_at ? ` · 拍摄 ${e(image.taken_at)}` : ""} · ${externalLink(image.source_url, "图片来源")}</figcaption></figure>`,
      )
      .join("");
  const menu = (item.menu_items || [])
    .map(
      (
        dish,
      ) => `<li class="detail-menu-row"><div><strong>${e(dish.dish_name)}</strong><span>${dish.price == null ? "单价暂未收录" : `¥${e(dish.price)} ${e(dish.price_unit)}`}</span></div>
    <small>${e(dish.price_note)} ${externalLink(dish.price_source_url, `价格来源 ${dish.price_checked_at || "日期未注明"}`)}</small></li>`,
    )
    .join("");
  return `<div class="detail-heading"><span class="eyebrow">RESTAURANT NOTES · 商家资料</span><h2>${e(item.name)}</h2><p>${e(districtLabel(item))} · ${e(item.cuisine_display || item.cuisine)}</p><strong class="merchant-price">${e(priceLabel(item))}</strong></div>
    <section class="detail-section"><h3>到店信息</h3><dl class="detail-facts">
      <div><dt>详细地址</dt><dd>${e(item.address || "门牌地址暂未收录")}</dd></div>
      <div><dt>营业时间</dt><dd>${e(item.opening_hours || "时间暂未收录，请联系门店确认")}</dd></div>
      <div><dt>联系电话</dt><dd>${item.phone_url ? externalLink(item.phone_url, item.phone) : e(item.phone || "电话暂未收录")}</dd></div>
      <div><dt>经纬坐标</dt><dd>${hasCoordinates(item) ? `${e(item.longitude)}, ${e(item.latitude)}（经度、纬度 · WGS84）` : "来源未提供可靠坐标，可按店名和地址查找"}</dd></div>
    </dl>${item.location_note ? `<p class="source-note">${e(item.location_note)}</p>` : ""}<div class="card-actions">${mapAction(item)}${externalLink(item.navigation_url, "打开导航 ↗", "button-secondary")}</div></section>
    <section class="detail-section"><div class="section-heading"><h3>菜单与参考价格</h3><span>按门店来源展示</span></div>
      ${
        dishes(item).length
          ? `<div class="condition-tags">${dishes(item)
              .map((dish) => `<span>${e(dish)}</span>`)
              .join("")}</div>`
          : ""
      }
      <ul class="detail-menu">${menu || '<li class="muted">该门店暂未收录有来源的菜单，可前往原始网页查看。</li>'}</ul><p class="source-note">来源参考价，实际售价、菜品供应及营业时间以门店为准。</p></section>
    ${images ? `<section class="detail-section"><h3>图片资料</h3><div class="evidence-gallery">${images}</div></section>` : ""}
    <details class="detail-provenance"><summary>资料来源与更新日期</summary><p>${e(item.quality_label)} · ${e(item.evidence_label)}</p>
      <p>${externalLink(item.source_url, item.source_name || "商家原始来源")}</p>
      ${item.evidence_url ? `<p>${externalLink(item.evidence_url, "查看归档证据")}</p>` : ""}
      ${item.source_updated_at ? `<p>源记录更新：${e(item.source_updated_at)}</p>` : ""}<p>网上收录不代表实时营业；资料未注明的内容保留为空。</p></details>
    <div class="detail-footer"><span>喜欢这家？把今晚的去处定下来。</span><button type="button" class="button-primary" data-choose="${item.id}">就选这家 →</button></div>`;
}

export function choiceView(item) {
  return `<span class="eyebrow">TONIGHT'S CHOICE · 今晚有着落了</span><h2>${e(item.name)}</h2><p>${e(item.address || item.district)} · ${e(priceLabel(item))}</p>
    <p class="source-note">${e(item.navigation_notice)}</p><div class="card-actions">${externalLink(item.navigation_url, "打开导航 ↗", "button-primary")}${externalLink(item.map_search_url, "在高德查看分店", "button-secondary")}
    ${item.phone_url ? externalLink(item.phone_url, `联系门店 ${item.phone}`, "button-secondary") : '<span class="source-note">门店电话暂未收录</span>'}${externalLink(item.source_url, "商家来源 ↗")}</div>
    <p class="source-note">营业与座位可在出发前向门店确认。导航和预订由外部平台提供，当前操作不会代为订座。</p>`;
}

export function comparisonView(items) {
  const rows = [
    ["参考价格", priceLabel],
    ["详细地址", (item) => item.address || "暂未收录"],
    ["菜系", (item) => item.cuisine_display || item.cuisine],
    ["招牌菜", (item) => dishes(item).join("、") || "暂未收录"],
    [
      "菜单价格",
      (item) =>
        (item.menu_items || [])
          .filter((dish) => dish.price != null)
          .map((dish) => `${dish.dish_name} ¥${dish.price} ${dish.price_unit}`)
          .join("；") || "单价暂未收录",
    ],
    [
      "直线距离",
      (item) =>
        item.distance_km != null ? `${item.distance_km} km` : "待提供出发位置",
    ],
    ["营业时间", (item) => item.opening_hours || "暂未收录"],
    ["联系电话", (item) => item.phone || "暂未收录"],
    ["资料来源", (item) => `${item.source_name} · ${item.evidence_label}`],
  ];
  return `<span class="eyebrow">SIDE BY SIDE · 一起比一比</span><h2>哪一家，更合今晚的心意？</h2><p class="muted">把价格、位置和口味放在一起，慢慢选。</p>
    <div class="comparison-scroll"><table><thead><tr><th>比较项目</th>${items.map((item) => `<th>${e(item.name)}</th>`).join("")}</tr></thead><tbody>
    ${rows.map(([label, render]) => `<tr><th>${label}</th>${items.map((item) => `<td>${e(render(item))}</td>`).join("")}</tr>`).join("")}
    <tr><th>作出选择</th>${items.map((item) => `<td><button type="button" class="button-primary" data-choose="${item.id}">就选这家</button></td>`).join("")}</tr></tbody></table></div>`;
}
