# E3 边裁定 · 逐条原文证据（19 行 / 9 条去重边）

生成脚本：`analysis/e3-blind/make_evidence.py`（只读仓库文件，可复跑复核）
判据版本：`C1-v1+C1a-20261027`
队列：`js-bloat-hybrid/runs/qualification-20261025-003/rq1/adjudication-queue.json`（19 行 → 9 条去重边）

> 本文件是 §5.2 要求的「全量证据披露」：把每条边的**两端源码原文**与**档案覆盖状态**一并公开，
> 使第三方在**没有第二名标注者**的情况下也能逐条复核。

## 汇总

| row_id | 边 | 类别 | 判定 | 出现臂 |
|---|---|---|---|---|
| `r01` | `string-tagcloud.js:231:1->string-tagcloud.js:235:18` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r02` | `string-tagcloud.js:231:1->string-tagcloud.js:231:1` | 同函数自环（不受 C1a 影响） | **FALSE** | `full`, `no-index`, `no-module-filter` |
| `r03` | `crypto-aes.js:343:1->crypto-aes.js:352:7` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r04` | `crypto-aes.js:359:1->crypto-aes.js:362:7` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r05` | `crypto-aes.js:359:1->crypto-aes.js:368:7` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r06` | `crypto-aes.js:282:1->crypto-aes.js:283:37` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r07` | `string-tagcloud.js:208:26->string-tagcloud.js:211:62` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r08` | `crypto-aes.js:278:1->crypto-aes.js:279:49` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |
| `r09` | `crypto-aes.js:343:1->crypto-aes.js:346:7` | 原生高阶方法的回调实参 | **TRUE** | `full`, `no-module-filter` |

判定分布（队列 19 行，按臂展开后）：**TRUE 16 / FALSE 3**（C1a-YES 口径）。
C1a-NO 口径下：回调实参类 8 条全部改为 FALSE，自环仍为 FALSE ⇒ **19 行全 FALSE**。

---

## 逐条证据

### `r01` — string-tagcloud.js:231:1->string-tagcloud.js:235:18

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`9634886bcb846c76141f97b681b33a11df444901e0b4c899d8f72a3b6544f9d5`

**端点 A** `string-tagcloud.js:231:1`

```
 231: function makeTagCloud(tagInfo)
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `string-tagcloud.js:235:18`

```
 235:     tagInfo.sort(function(a, b) { if (a.tag < b.tag) { return -1; } else if (a.tag == b.tag) { return 0; } else return 1; });
```
第 18 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 235 行第 18 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r02` — string-tagcloud.js:231:1->string-tagcloud.js:231:1

- **类别**：同函数自环（不受 C1a 影响）
- **判定（C1a-YES）**：**FALSE**
- **出现臂**：`full`, `no-index`, `no-module-filter`
- **源文件 sha256**：`9634886bcb846c76141f97b681b33a11df444901e0b4c899d8f72a3b6544f9d5`

**端点 A** `string-tagcloud.js:231:1`

```
 231: function makeTagCloud(tagInfo)
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `string-tagcloud.js:231:1`

```
 231: function makeTagCloud(tagInfo)
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（自环，不需要 C1a）**：两端位置字符串指向**同一个函数** `makeTagCloud`（声明于 `string-tagcloud.js:231`，函数体至第 262 行）。该函数体内**不存在对自身的调用**；逐一枚举其调用点为：

- 第 235 行：`tagInfo.sort(function(a, b) { if (a.tag < b.tag) { return -1; } else if (a.tag == b.tag) { return 0; } else return 1; });`
- 第 242 行：`var ch = tag.charCodeAt(j);`
- 第 252 行：`var url = "http://example.com/tag/" + tag.replace(" ", "").toLowerCase();`
- 第 254 行：`var color = 'rgb(' + Math.floor(255 * (popularity - 12) / 20) + ', 0, 255)';`
- 第 259 行：`output.replace(" ", "&nbsp;");`

⇒ 该函数既无直接递归也无多态递归（第 231 行为普通函数声明，未被赋给任何对象属性），**不存在从其自身到自身的调用路径**，故判 **FALSE**。

根因是位置渲染把原生被调顶点折叠到宿主函数位置（`experiments/rq1/single_benchmark.js:31-34`），已记为工具缺陷（本文 §9.2，本轮不修）。

---

### `r03` — crypto-aes.js:343:1->crypto-aes.js:352:7

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`7151c362dd1d10ec6bf8bd332a57bf96aa3d6bf64a87695b7b670af09e430365`

**端点 A** `crypto-aes.js:343:1`

```
 343: function encodeUTF8(str) {  // encode multi-byte string into utf-8 multiple single-byte characters 
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `crypto-aes.js:352:7`

```
 352:       function(c) { 
```
第 7 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 352 行第 7 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r04` — crypto-aes.js:359:1->crypto-aes.js:362:7

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`7151c362dd1d10ec6bf8bd332a57bf96aa3d6bf64a87695b7b670af09e430365`

**端点 A** `crypto-aes.js:359:1`

```
 359: function decodeUTF8(str) {  // decode utf-8 encoded string back into multi-byte characters
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `crypto-aes.js:362:7`

```
 362:       function(c) { 
```
第 7 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 362 行第 7 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r05` — crypto-aes.js:359:1->crypto-aes.js:368:7

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`7151c362dd1d10ec6bf8bd332a57bf96aa3d6bf64a87695b7b670af09e430365`

**端点 A** `crypto-aes.js:359:1`

```
 359: function decodeUTF8(str) {  // decode utf-8 encoded string back into multi-byte characters
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `crypto-aes.js:368:7`

```
 368:       function(c) { 
```
第 7 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 368 行第 7 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r06` — crypto-aes.js:282:1->crypto-aes.js:283:37

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`7151c362dd1d10ec6bf8bd332a57bf96aa3d6bf64a87695b7b670af09e430365`

**端点 A** `crypto-aes.js:282:1`

```
 282: function unescCtrlChars(str) {  // unescape potentially problematic control characters
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `crypto-aes.js:283:37`

```
 283:   return str.replace(/!\d\d?\d?!/g, function(c) { return String.fromCharCode(c.slice(1,-1)); });
```
第 37 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 283 行第 37 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r07` — string-tagcloud.js:208:26->string-tagcloud.js:211:62

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`9634886bcb846c76141f97b681b33a11df444901e0b4c899d8f72a3b6544f9d5`

**端点 A** `string-tagcloud.js:208:26`

```
 208:         s.toJSONString = function () {
```
第 26 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `string-tagcloud.js:211:62`

```
 211:                 return '"' + this.replace(/[\x00-\x1f\\"]/g, function (a) {
```
第 62 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 211 行第 62 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r08` — crypto-aes.js:278:1->crypto-aes.js:279:49

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`7151c362dd1d10ec6bf8bd332a57bf96aa3d6bf64a87695b7b670af09e430365`

**端点 A** `crypto-aes.js:278:1`

```
 278: function escCtrlChars(str) {  // escape control chars which might cause problems handling ciphertext
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `crypto-aes.js:279:49`

```
 279:   return str.replace(/[\0\t\n\v\f\r\xa0'"!-]/g, function(c) { return '!' + c.charCodeAt(0) + '!'; });
```
第 49 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 279 行第 49 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

### `r09` — crypto-aes.js:343:1->crypto-aes.js:346:7

- **类别**：原生高阶方法的回调实参
- **判定（C1a-YES）**：**TRUE**
- **出现臂**：`full`, `no-module-filter`
- **源文件 sha256**：`7151c362dd1d10ec6bf8bd332a57bf96aa3d6bf64a87695b7b670af09e430365`

**端点 A** `crypto-aes.js:343:1`

```
 343: function encodeUTF8(str) {  // encode multi-byte string into utf-8 multiple single-byte characters 
```
第 1 列实际字符 = `f`
档案中是否为节点：**是**

**端点 B** `crypto-aes.js:346:7`

```
 346:       function(c) { 
```
第 7 列实际字符 = `f`
档案中是否为节点：**否**

档案中是否存在该 link：**否** ⇒ 结构上不可能被档案判定，故为 `unjudged` 而非假阳性

**判定理由（C1a）**：端点 B 是**函数字面量**，且词法上位于端点 A 体内一次调用 `M(...)` 的**实参位置**（第 346 行第 7 列的实际字符为 `f`，即 `function` 关键字起始处）。
`M` 属于 C1a 覆盖的两个内置方法之一（`String.prototype.replace` / `Array.prototype.sort`），语言规范保证其**必然调用**该函数实参，因此 A → B 构成一条可静态解析的调用路径。

注：端点 B **不是**档案节点，说明档案不建模此类回调字面量（本文 §2.3）；因此本判定依赖 C1a，而非档案。

---

## C1a 不被采纳时（C1a-NO）的差异

上表 8 条「原生高阶方法的回调实参」边在 C1a-NO 下**全部记为 FALSE**；
自环边 `string-tagcloud.js:231:1->string-tagcloud.js:231:1` 在两种口径下**均为 FALSE**（不依赖 C1a）。

因此两口径的差别**恰好且仅为**这 8 条边，见本文 §9.1 的双口径敏感度表。

## 与档案自身约定的关系

`datasets/manifests/static-benchmark.json` 的 `limitations` 原文：

> Absent-from-annotation predictions are unjudged, not false positives.

本文件对每条边都给出了「档案是否存在该 link」的实测结果，正是为了让第三方能够验证：这些边的 `unjudged` 状态来自**档案覆盖缺口**，而不是来自任何争议。
