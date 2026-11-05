/* Pure HTML renderers. API calls and mutable page state belong in app.js. */
export function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char],
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
          ? "来源菜品价格区间"
          : "来源价格区间（单位待确认）";
    return `${basis} ¥${item.price_range_min}–${item.price_range_max}`;
  }
  return item.price_per_person != null
    ? `参考人均 ¥${item.price_per_person}`
    : "人均价格待确认";
}

export function constraintsView(context, budgetPerPerson) {
  if (!context)
    return "<p>说出人数、预算、出发位置和到店时间；没有口味要求也可以。</p>";
  const labels = [
    context.party_size ? `${context.party_size} 人` : "人数待确认",
    context.budget != null
      ? `${context.budget_kind === "total" ? "总预算" : context.budget_kind === "per_person" ? "人均" : "预算单位待确认"} ¥${context.budget}`
      : "预算待确认",
    context.location?.name || "位置待确认",
    context.arrival
      ? `${context.arrival.slice(0, 16).replace("T", " ")}（北京时间${context.arrival_date_inferred ? "，日期按今天推定" : ""}）`
      : "到店时间待确认",
    context.cuisine || "不限口味",
    context.radius_km ? `直线距离 ≤ ${context.radius_km} km` : "",
    context.avoid?.length ? `忌口：${context.avoid.join("、")}` : "",
    context.wait_minutes != null
      ? `希望等位 ≤ ${context.wait_minutes} 分钟`
      : "",
  ].filter(Boolean);
  const derived =
    context.budget_kind === "total" && budgetPerPerson != null
      ? `<p>按 ${context.party_size} 人推算人均上限约 ¥${budgetPerPerson.toFixed(2)}，最终消费需向门店核实。</p>`
      : "";
  return `<div class="condition-tags">${labels.map((label) => `<span>${e(label)}</span>`).join("")}</div>${derived}<p>${e(context.location?.note || "")}</p>`;
}

export function merchantCards(items, saved, compared, showKeep = false) {
  if (!items.length)
    return '<p class="empty-state">这里暂时没有可展示的门店。</p>';
  return items
    .map(
      (item, index) => `<article class="decision-card" data-card="${item.id}">
    <div class="decision-card-heading"><span class="eyebrow">${index + 1} · ${e(item.quality_label || "公开来源资料")}</span>
      <h2>${e(item.name)}</h2></div>
    <p>${e(item.district)} · ${e(item.address)}</p>
    <div class="condition-tags"><span>${e(priceLabel(item))}</span><span>${e(item.cuisine_display || item.cuisine)}</span>
      <span>${item.distance_km != null ? `约 ${e(item.distance_km)} km · 直线` : "距离待确认"}</span></div>
    ${item.estimated_total != null ? `<p>按来源参考价估算本次约 ¥${e(item.estimated_total)}，实际消费需向门店确认。</p>` : ""}
    ${item.reasons?.length ? `<h3>选择依据</h3><ul>${item.reasons.map((text) => `<li>${e(text)}</li>`).join("")}</ul>` : ""}
    ${item.questions?.length ? `<div class="confirmation-note"><strong>出发前需确认</strong><ul>${item.questions.map((text) => `<li>${e(text)}</li>`).join("")}</ul></div>` : ""}
    <p class="source-note">${e(item.evidence_label || "日期待确认")} · ${externalLink(item.source_url, item.source_name || "查看来源")}</p>
    <p class="source-note">${(item.priced_menu || []).length ? item.priced_menu.map((dish) => `${e(dish.dish_name)} ¥${e(dish.price)} ${e(dish.price_unit)}`).join(" · ") : "暂无可核验单品价格"}</p>
    <div class="card-actions">
      <button type="button" data-detail="${item.id}">菜单与资料</button>
      <button type="button" data-save="${item.id}" aria-pressed="${saved.has(item.id)}">${saved.has(item.id) ? "♥ 已收藏" : "♡ 收藏"}</button>
      <button type="button" data-compare="${item.id}" aria-pressed="${compared.has(item.id)}">${compared.has(item.id) ? "✓ 已选对比" : "加入对比"}</button>
      ${showKeep ? `<button type="button" data-keep="${item.id}" aria-pressed="${!!item.kept}">${item.kept ? "✓ 下轮保留" : "下轮保留"}</button>` : ""}
      <button type="button" class="button-primary" data-choose="${item.id}">就选这家</button>
    </div></article>`,
    )
    .join("");
}

export function detailsView(item) {
  const images =
    (item.photos || [])
      .map(
        (photo) =>
          `<figure><img src="${e(photo.photo_url)}" alt="门店授权照片" loading="lazy"><figcaption>拍摄 ${e(photo.taken_at)} · ${e(photo.copyright_holder)}</figcaption></figure>`,
      )
      .join("") +
    (item.images || [])
      .map(
        (image) =>
          `<figure><img src="${e(image.image_url)}" alt="${e(image.caption)}" loading="lazy"><figcaption>${e(image.image_type === "dish_reference" ? "菜品参考图，非该分店实拍 · " : "")}${e(image.caption)} · ${e(image.author)} · ${e(image.license)} · 拍摄 ${e(image.taken_at)} · ${externalLink(image.source_url, "图片来源")}</figcaption></figure>`,
      )
      .join("");
  const menu = (item.menu_items || [])
    .map(
      (
        dish,
      ) => `<li><strong>${e(dish.dish_name)}</strong> · ${dish.price == null ? "单价待确认" : `¥${e(dish.price)} ${e(dish.price_unit)}`}<br>
    <small>${e(dish.price_note)} ${externalLink(dish.price_source_url, `价格来源 ${dish.price_checked_at || "日期未注明"}`)}</small></li>`,
    )
    .join("");
  return `<h2>${e(item.name)}</h2><p>${e(item.district)} · ${e(item.address)}</p>
    <p>${e(priceLabel(item))} · ${e(item.quality_label)}</p>
    <p>营业资料：${e(item.opening_hours || "尚未收录，请联系门店确认")}</p>
    <p>${e(item.location_note || "")}</p><div class="evidence-gallery">${images}</div>
    <h3>菜单与价格来源</h3><ul>${menu || "<li>暂无带近期来源的菜单资料，请向门店确认。</li>"}</ul>
    <p>${e(item.evidence_label)} · ${externalLink(item.source_url, "原始商家来源")}</p>
    ${item.evidence_url ? `<p>${externalLink(item.evidence_url, "采集或归档证据")}</p>` : ""}
    <p>坐标：${item.latitude != null && item.longitude != null ? `${e(item.latitude)}, ${e(item.longitude)}（纬度、经度，WGS84）` : "来源未提供可靠坐标"}</p>
    <button class="button-primary" data-choose="${item.id}">就选这家</button>`;
}

export function choiceView(item) {
  return `<h2>已选择：${e(item.name)}</h2><p>${e(item.district)} · ${e(item.address)}</p>
    <p>${e(priceLabel(item))}；实际价格、营业及座位请出发前核实。</p>
    ${item.questions?.length ? `<ul>${item.questions.map((question) => `<li>${e(question)}</li>`).join("")}</ul>` : ""}
    <p>${e(item.navigation_notice)}</p>
    <div class="card-actions">${externalLink(item.navigation_url, "打开步行导航", "button-primary")}
      ${externalLink(item.map_search_url, "在高德核对分店")}
      ${item.phone_url ? externalLink(item.phone_url, `联系门店 ${item.phone}`) : "<span>暂未收录可靠联系电话</span>"}
      ${externalLink(item.source_url, "查看门店来源")}</div>
    <p class="source-note">导航交由地图应用处理。外部来源链接用于核实资料，不表示已经订座。</p>`;
}

export function comparisonView(items) {
  const rows = [
    ["参考人均", (item) => priceLabel(item)],
    ["地址", (item) => item.address],
    ["菜系", (item) => item.cuisine_display || item.cuisine],
    [
      "直线距离",
      (item) =>
        item.distance_km != null ? `${item.distance_km} km` : "待确认",
    ],
    ["营业资料", (item) => item.opening_hours || "待确认"],
    ["来源证据日期", (item) => item.evidence_label],
    ["资料状态", (item) => item.quality_label],
    [
      "仍需确认",
      (item) => item.questions?.join("；") || "营业、价格及座位请向门店确认",
    ],
  ];
  return `<h2>放在一起，选更适合的一家</h2><p>比较来源事实，不生成虚构评分或实时排队信息。</p>
    <div class="comparison-scroll"><table><thead><tr><th>比较项目</th>${items.map((item) => `<th>${e(item.name)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(([label, render]) => `<tr><th>${label}</th>${items.map((item) => `<td>${e(render(item))}</td>`).join("")}</tr>`).join("")}
    <tr><th>作出选择</th>${items.map((item) => `<td><button class="button-primary" data-choose="${item.id}">就选这家</button></td>`).join("")}</tr></tbody></table></div>`;
}
