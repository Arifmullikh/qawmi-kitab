# An Nur অ্যাপে "কওমি কিতাব" — Android (Kotlin) ইমপ্লিমেন্টেশন

এই কোড কপি-পেস্ট করলেই অ্যাপের "কওমি কিতাব" অংশ চালু হবে:

- জামাতের তালিকা (মারহালা ও তাখাসসুস আলাদা) → জামাত চাপলে **বাংলা** / **মূল কিতাব** দুই ট্যাব
- তালিকা সরাসরি GitHub থেকে আসে, তাই GitHub-এ কিতাব যোগ/মুছলে অ্যাপ আপডেট ছাড়াই বদলে যায়
- ক্যাশ + ETag ব্যবহার করে, তাই টোকেন ছাড়া ঘণ্টায় ৬০ কলের লিমিটে আটকায় না; লিমিট শেষ হলে বা ইন্টারনেট না থাকলে শেষ ক্যাশ দেখায়
- PDF অ্যাপের নিজের স্টোরেজে নামে (অফলাইনে পড়া যায়), তারপর ফোনের PDF রিডারে খোলে
- একটা বই কয়েক ভাগে (`_part01of03`) থাকলে অ্যাপে এক কিতাব হিসেবে দেখায়

ডেটা কোথা থেকে আসে (ক্রম অনুযায়ী):
1. **লাইভ:** `GET https://api.github.com/repos/Arifmullikh/qawmi-kitab/releases?per_page=100` + `jamats.json` + `names.json` (raw)। ETag দিয়ে পাঠানো হয়; কিছু না বদলালে GitHub `304` দেয়, যেটা রেট লিমিটে গোনা হয় না।
2. **ব্যাকআপ:** `https://raw.githubusercontent.com/Arifmullikh/qawmi-kitab/main/catalog.json` (রেট লিমিট নেই, GitHub Action ৩০ মিনিট পরপর বানায়)।
3. **অফলাইন:** শেষবার সফলভাবে আনা ডেটা (ফাইলে সেভ করা)।

---

## ১. Gradle dependency (`app/build.gradle.kts`)

```kotlin
dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    // Jetpack Compose (নতুন Android Studio প্রজেক্টে সাধারণত আগেই থাকে)
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.compose.material3:material3")
}
```

JSON পার্স করতে Android-এর বিল্ট-ইন `org.json` ব্যবহার করা হয়েছে, আলাদা লাইব্রেরি লাগবে না।

## ২. `AndroidManifest.xml`

```xml
<uses-permission android:name="android.permission.INTERNET" />

<application ...>
    <provider
        android:name="androidx.core.content.FileProvider"
        android:authorities="${applicationId}.fileprovider"
        android:exported="false"
        android:grantUriPermissions="true">
        <meta-data
            android:name="android.support.FILE_PROVIDER_PATHS"
            android:resource="@xml/qk_file_paths" />
    </provider>
</application>
```

`res/xml/qk_file_paths.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<paths>
    <files-path name="kitab" path="kitab/" />
</paths>
```

## ৩. মডেল + রিপোজিটরি (`qawmikitab/QawmiKitabRepository.kt`)

```kotlin
package com.annur.app.qawmikitab   // তোমার প্যাকেজ নাম দাও

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

data class KitabPart(val name: String, val part: Int, val size: Long, val url: String)

data class Kitab(
    val id: String,          // "<tag>/<base filename>"
    val tag: String,
    val section: String,     // "bangla" | "original"
    val title: String,       // বাংলা নাম
    val lang: String?,       // bn | ar | ur | fa
    val size: Long,
    val parts: List<KitabPart>
)

data class Jamat(
    val tag: String, val nameBn: String, val group: String, val order: Int,
    val books: List<Kitab>
) {
    val bangla get() = books.filter { it.section == "bangla" }
    val original get() = books.filter { it.section == "original" }
}

data class Catalog(val jamats: List<Jamat>, val fetchedAt: Long, val fromCache: Boolean)

class QawmiKitabRepository(context: Context) {
    companion object {
        const val REPO = "Arifmullikh/qawmi-kitab"
        const val RAW = "https://raw.githubusercontent.com/$REPO/main"
        const val API_RELEASES = "https://api.github.com/repos/$REPO/releases?per_page=100"
        private const val CACHE_MAX_AGE_MS = 10 * 60 * 1000L     // ১০ মিনিটের মধ্যে আবার নেটে যাবে না
        private val PART = Regex("^(.+?)_part(\\d+)of(\\d+)\\.pdf$", RegexOption.IGNORE_CASE)
    }

    private val appCtx = context.applicationContext
    private val dir = File(appCtx.filesDir, "qk").apply { mkdirs() }
    private val http = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()

    /** অ্যাপ খুললে load(false); pull-to-refresh এ load(true) */
    suspend fun load(force: Boolean = false): Catalog = withContext(Dispatchers.IO) {
        val cached = File(dir, "catalog_cache.json")
        if (!force && cached.exists() && System.currentTimeMillis() - cached.lastModified() < CACHE_MAX_AGE_MS) {
            return@withContext parseCatalogJson(JSONObject(cached.readText()), cached.lastModified(), true)
        }
        // ১) লাইভ: Releases API (+ETag)
        runCatching { buildFromApi() }.getOrNull()?.let { json ->
            cached.writeText(json.toString()); return@withContext parseCatalogJson(json, System.currentTimeMillis(), false)
        }
        // ২) ব্যাকআপ: catalog.json
        runCatching { getText("$RAW/catalog.json")!! }.getOrNull()?.let { txt ->
            cached.writeText(txt); return@withContext parseCatalogJson(JSONObject(txt), System.currentTimeMillis(), false)
        }
        // ৩) অফলাইন ক্যাশ
        if (cached.exists()) return@withContext parseCatalogJson(JSONObject(cached.readText()), cached.lastModified(), true)
        throw java.io.IOException("ইন্টারনেট সংযোগ নেই, আর আগের কোনো ডেটাও সেভ নেই")
    }

    /** GET with ETag cache. 304 হলে আগের বডি ফেরত দেয় (রেট লিমিটে গোনা হয় না)। */
    private fun getText(url: String, etagKey: String? = null): String? {
        val bodyFile = etagKey?.let { File(dir, "$it.body") }
        val etagFile = etagKey?.let { File(dir, "$it.etag") }
        val rb = Request.Builder().url(url).header("User-Agent", "AnNur-App")
        if (url.startsWith("https://api.github.com")) rb.header("Accept", "application/vnd.github+json")
        if (etagFile?.exists() == true && bodyFile?.exists() == true) rb.header("If-None-Match", etagFile.readText())
        http.newCall(rb.build()).execute().use { r ->
            if (r.code == 304 && bodyFile != null) return bodyFile.readText()
            if (r.code == 403 || r.code == 429) {
                // রেট লিমিট শেষ (X-RateLimit-Remaining: 0) → কল করা ব্যর্থ, উপরের লেয়ার catalog.json/ক্যাশে যাবে
                throw java.io.IOException("GitHub rate limit, resets at ${r.header("X-RateLimit-Reset")}")
            }
            if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code} $url")
            val txt = r.body!!.string()
            if (etagKey != null) { bodyFile!!.writeText(txt); r.header("ETag")?.let { etagFile!!.writeText(it) } }
            return txt
        }
    }

    /** Releases API + jamats.json + names.json থেকে catalog.json-এর মতো একই আকারের JSON বানায় */
    private fun buildFromApi(): JSONObject {
        val releases = JSONArray(getText(API_RELEASES, "releases")!!)
        val jamatsJson = JSONObject(getText("$RAW/jamats.json", "jamats")!!).getJSONArray("jamats")
        val names = runCatching { JSONObject(getText("$RAW/names.json", "names")!!) }.getOrElse { JSONObject() }

        val relByTag = (0 until releases.length()).map { releases.getJSONObject(it) }
            .filter { !it.optBoolean("draft") }.associateBy { it.getString("tag_name") }
        val jamatList = (0 until jamatsJson.length()).map { jamatsJson.getJSONObject(it) }.toMutableList()
        // jamats.json এ নেই এমন নতুন রিলিজও শেষে দেখাও
        relByTag.keys.filter { t -> jamatList.none { it.getString("tag") == t } }.forEachIndexed { i, t ->
            jamatList += JSONObject().put("tag", t).put("name_bn", relByTag[t]!!.optString("name", t))
                .put("group", "other").put("order", 1000 + i)
        }
        val out = JSONArray()
        for (j in jamatList) {
            val tag = j.getString("tag")
            val books = linkedMapOf<String, JSONObject>()
            val assets = relByTag[tag]?.optJSONArray("assets") ?: JSONArray()
            for (k in 0 until assets.length()) {
                val a = assets.getJSONObject(k)
                val name = a.getString("name")
                if (a.optString("state") != "uploaded" || !name.endsWith(".pdf", true)) continue
                val m = PART.matchEntire(name)
                val base = if (m != null) m.groupValues[1] + ".pdf" else name
                val section = if (name.startsWith("Bangla__")) "bangla" else "original"
                val meta = names.optJSONObject("$tag/$name") ?: names.optJSONObject("$tag/$base")
                val b = books.getOrPut(base) {
                    JSONObject().put("id", "$tag/$base").put("section", section)
                        .put("title", meta?.optString("title")?.takeIf { it.isNotBlank() } ?: prettify(base))
                        .put("lang", meta?.optString("lang") ?: if (section == "bangla") "bn" else JSONObject.NULL)
                        .put("size", 0L).put("parts", JSONArray())
                }
                b.getJSONArray("parts").put(JSONObject().put("name", name)
                    .put("part", m?.groupValues?.get(2)?.toInt() ?: 1)
                    .put("size", a.getLong("size")).put("url", a.getString("browser_download_url")))
                b.put("size", b.getLong("size") + a.getLong("size"))
            }
            out.put(JSONObject(j.toString()).put("books", JSONArray(books.values.toList())))
        }
        return JSONObject().put("schema", 1).put("jamats", out)
    }

    private fun parseCatalogJson(root: JSONObject, ts: Long, fromCache: Boolean): Catalog {
        val ja = root.getJSONArray("jamats")
        val jamats = (0 until ja.length()).map { i ->
            val j = ja.getJSONObject(i); val tag = j.getString("tag")
            val ba = j.optJSONArray("books") ?: JSONArray()
            val books = (0 until ba.length()).map { k ->
                val b = ba.getJSONObject(k); val pa = b.getJSONArray("parts")
                Kitab(b.getString("id"), tag, b.getString("section"), b.getString("title"),
                    if (b.isNull("lang")) null else b.optString("lang").ifBlank { null }, b.getLong("size"),
                    (0 until pa.length()).map { p -> pa.getJSONObject(p).let {
                        KitabPart(it.getString("name"), it.optInt("part", 1), it.getLong("size"), it.getString("url")) }
                    }.sortedBy { it.part })
            }.sortedBy { it.id }
            Jamat(tag, j.optString("name_bn", tag), j.optString("group", "other"), j.optInt("order", 999), books)
        }.sortedBy { it.order }
        return Catalog(jamats, ts, fromCache)
    }

    private fun prettify(file: String) = file.removePrefix("Bangla__").removePrefix("Original__")
        .removeSuffix(".pdf").replace(Regex("^[0-9]+[a-z]?[-_]"), "").replace(Regex("[-_]+"), " ").trim()
}
```

## ৪. ডাউনলোড + খোলা (`qawmikitab/KitabDownloader.kt`)

```kotlin
package com.annur.app.qawmikitab

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.widget.Toast
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

class KitabDownloader(context: Context) {
    private val ctx = context.applicationContext
    private val http = OkHttpClient.Builder().connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.MINUTES).followRedirects(true).build()   // GitHub ডাউনলোড রিডাইরেক্ট করে

    fun partFile(k: Kitab, p: KitabPart) = File(ctx.filesDir, "kitab/${k.tag}/${p.name}")
    fun isDownloaded(k: Kitab) = k.parts.all { partFile(k, it).let { f -> f.exists() && f.length() == it.size } }
    fun delete(k: Kitab) = k.parts.forEach { partFile(k, it).delete() }

    /** সব পার্ট ডাউনলোড করে; onProgress(0f..1f)। আংশিক ডাউনলোড থাকলে Range দিয়ে বাকিটা নেয়। */
    suspend fun download(k: Kitab, onProgress: (Float) -> Unit) = withContext(Dispatchers.IO) {
        var done = 0L
        for (p in k.parts) {
            val f = partFile(k, p); f.parentFile?.mkdirs()
            if (f.exists() && f.length() == p.size) { done += p.size; onProgress(done.toFloat() / k.size); continue }
            val tmp = File(f.path + ".part")
            val have = if (tmp.exists()) tmp.length() else 0L
            val req = Request.Builder().url(p.url).apply { if (have > 0) header("Range", "bytes=$have-") }.build()
            http.newCall(req).execute().use { r ->
                if (!r.isSuccessful) throw java.io.IOException("ডাউনলোড ব্যর্থ: HTTP ${r.code}")
                val append = have > 0 && r.code == 206
                var got = if (append) have else 0L
                r.body!!.byteStream().use { input ->
                    java.io.FileOutputStream(tmp, append).use { out ->
                        val buf = ByteArray(64 * 1024)
                        while (true) {
                            val n = input.read(buf); if (n < 0) break
                            out.write(buf, 0, n); got += n
                            onProgress((done + got).toFloat() / k.size)
                        }
                    }
                }
            }
            tmp.renameTo(f); done += p.size
        }
    }

    /** ফোনের PDF রিডারে খোলে। পার্ট একাধিক হলে partIndex দিয়ে কোনটা খুলবে বলো। */
    fun open(k: Kitab, partIndex: Int = 0) {
        val f = partFile(k, k.parts[partIndex])
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", f)
        val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/pdf")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        try { ctx.startActivity(i) } catch (e: ActivityNotFoundException) {
            Toast.makeText(ctx, "PDF পড়ার অ্যাপ নেই (যেমন Google PDF Viewer ইনস্টল করো)", Toast.LENGTH_LONG).show()
        }
    }
}

fun Long.readableSize(): String = when {
    this >= 1L shl 30 -> "%.1f GB".format(this / (1L shl 30).toDouble())
    this >= 1L shl 20 -> "%.1f MB".format(this / (1L shl 20).toDouble())
    else -> "%d KB".format(this / 1024)
}
```

> অ্যাপের ভেতরেই PDF দেখাতে চাইলে Android-এর `android.graphics.pdf.PdfRenderer` দিয়ে `partFile(...)` খুলে পেজগুলো Bitmap হিসেবে দেখাতে পারো; অথবা নিজের অ্যাপে আগে থেকে PDF ভিউয়ার থাকলে সেখানে `partFile(...)` এর path পাঠাও।

## ৫. ViewModel + Compose স্ক্রিন (`qawmikitab/QawmiKitabScreens.kt`)

```kotlin
package com.annur.app.qawmikitab

import android.app.Application
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

class QawmiKitabViewModel(app: Application) : AndroidViewModel(app) {
    val repo = QawmiKitabRepository(app)
    val dl = KitabDownloader(app)
    val catalog = MutableStateFlow<Catalog?>(null)
    val error = MutableStateFlow<String?>(null)
    val loading = MutableStateFlow(false)
    val progress = MutableStateFlow<Map<String, Float>>(emptyMap())   // kitab.id -> 0..1
    val tick = MutableStateFlow(0)                                     // ডাউনলোড শেষে UI রিফ্রেশ

    init { refresh(false) }

    fun refresh(force: Boolean) = viewModelScope.launch {
        loading.value = true; error.value = null
        runCatching { repo.load(force) }.onSuccess { catalog.value = it }.onFailure { error.value = it.message }
        loading.value = false
    }

    fun downloadOrOpen(k: Kitab, part: Int = 0) {
        if (dl.isDownloaded(k)) { dl.open(k, part); return }
        if (progress.value.containsKey(k.id)) return
        viewModelScope.launch {
            progress.value = progress.value + (k.id to 0f)
            runCatching { dl.download(k) { p -> progress.value = progress.value + (k.id to p) } }
                .onSuccess { dl.open(k, part) }.onFailure { error.value = it.message }
            progress.value = progress.value - k.id; tick.value++
        }
    }
}

/** নেভিগেশনে এটাকেই "কওমি কিতাব" রুট হিসেবে বসাও */
@Composable
fun QawmiKitabRoute(vm: QawmiKitabViewModel = viewModel()) {
    var selected by remember { mutableStateOf<String?>(null) }
    val cat by vm.catalog.collectAsState()
    val jamat = cat?.jamats?.firstOrNull { it.tag == selected }
    if (jamat == null) JamatListScreen(vm) { selected = it }
    else {
        androidx.activity.compose.BackHandler { selected = null }
        JamatScreen(vm, jamat) { selected = null }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JamatListScreen(vm: QawmiKitabViewModel, onOpen: (String) -> Unit) {
    val cat by vm.catalog.collectAsState(); val loading by vm.loading.collectAsState(); val err by vm.error.collectAsState()
    Scaffold(topBar = { TopAppBar(title = { Text("কওমি কিতাব") }, actions = {
        TextButton(onClick = { vm.refresh(true) }) { Text("রিফ্রেশ") } }) }) { pad ->
        Column(Modifier.padding(pad)) {
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            err?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(12.dp)) }
            if (cat?.fromCache == true) Text("অফলাইন/ক্যাশ থেকে দেখানো হচ্ছে", style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 12.dp))
            val groups = cat?.jamats.orEmpty().groupBy { it.group }
            LazyColumn {
                for ((g, list) in groups) {
                    item { Text(when (g) { "marhala" -> "জামাত (মারহালা)"; "takhassus" -> "তাখাসসুস"; else -> "অন্যান্য" },
                        style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(16.dp, 16.dp, 16.dp, 4.dp)) }
                    items(list, key = { it.tag }) { j ->
                        ListItem(headlineContent = { Text(j.nameBn) },
                            supportingContent = { Text("বাংলা ${j.bangla.size} • মূল ${j.original.size} টি কিতাব") },
                            modifier = Modifier.clickable { onOpen(j.tag) })
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JamatScreen(vm: QawmiKitabViewModel, jamat: Jamat, onBack: () -> Unit) {
    var tab by remember { mutableIntStateOf(0) }
    val prog by vm.progress.collectAsState(); vm.tick.collectAsState()
    val list = if (tab == 0) jamat.bangla else jamat.original
    var partPicker by remember { mutableStateOf<Kitab?>(null) }
    Scaffold(topBar = { TopAppBar(title = { Text(jamat.nameBn) },
        navigationIcon = { TextButton(onClick = onBack) { Text("‹ ফিরে") } }) }) { pad ->
        Column(Modifier.padding(pad)) {
            TabRow(selectedTabIndex = tab) {
                Tab(tab == 0, { tab = 0 }, text = { Text("বাংলা (${jamat.bangla.size})") })
                Tab(tab == 1, { tab = 1 }, text = { Text("মূল কিতাব (${jamat.original.size})") })
            }
            if (list.isEmpty()) Text("এখনো কোনো কিতাব নেই", Modifier.padding(24.dp))
            LazyColumn {
                items(list, key = { it.id }) { k ->
                    val p = prog[k.id]; val done = vm.dl.isDownloaded(k)
                    ListItem(
                        headlineContent = { Text(k.title) },
                        supportingContent = {
                            Column {
                                Text(buildString {
                                    append(k.size.readableSize())
                                    if (k.parts.size > 1) append(" • ${k.parts.size} ভাগ")
                                    k.lang?.let { append(" • " + mapOf("bn" to "বাংলা", "ar" to "আরবি", "ur" to "উর্দু", "fa" to "ফারসি").getOrElse(it) { it }) }
                                })
                                if (p != null) LinearProgressIndicator(progress = { p }, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
                            }
                        },
                        trailingContent = { Text(if (p != null) "${(p * 100).toInt()}%" else if (done) "খুলুন" else "ডাউনলোড") },
                        modifier = Modifier.clickable {
                            if (done && k.parts.size > 1) partPicker = k else vm.downloadOrOpen(k)
                        })
                    HorizontalDivider()
                }
            }
        }
    }
    partPicker?.let { k ->
        AlertDialog(onDismissRequest = { partPicker = null }, confirmButton = {},
            title = { Text(k.title) },
            text = { Column { k.parts.forEachIndexed { i, _ ->
                TextButton(onClick = { partPicker = null; vm.downloadOrOpen(k, i) }) { Text("ভাগ ${i + 1} খুলুন") } } } })
    }
}
```

নেভিগেশনে বসানো (উদাহরণ): `composable("qawmi_kitab") { QawmiKitabRoute() }` — অথবা যে Activity/Fragment-এ "কওমি কিতাব" অপশন আছে সেখানে `setContent { QawmiKitabRoute() }`।

---

## JSON স্কিমা (Flutter / React Native / অন্য স্ট্যাকের জন্য)

### `jamats.json`
```jsonc
{
  "version": 1,
  "repo": "Arifmullikh/qawmi-kitab",
  "groups": { "marhala": "মারহালা (জামাত)", "takhassus": "তাখাসসুস" },
  "jamats": [
    { "order": 1, "tag": "taisir", "name_bn": "তাইসীর", "name_en": "Taisir", "group": "marhala" }
  ]
}
```
`tag` = GitHub release-এর tag। `order` অনুযায়ী সাজাও।

### `names.json`
```jsonc
{ "<tag>/<asset ফাইলের নাম>": { "title": "বাংলা নাম", "lang": "bn|ar|ur|fa" } }
```
এন্ট্রি না থাকলে ফাইলের নাম থেকে নাম বানাও: `Bangla__`/`Original__` আর `.pdf` বাদ, শুরুর নম্বর বাদ, `-`/`_` → স্পেস। মাল্টি-পার্ট ফাইলের জন্য `<tag>/<base>.pdf` (পার্ট সাফিক্স ছাড়া) কি-ও দেখো।

### Releases API (`GET https://api.github.com/repos/Arifmullikh/qawmi-kitab/releases?per_page=100`)
শুধু এই ফিল্ডগুলো লাগবে: `tag_name`, `name` (বাংলা টাইটেল), `assets[].name`, `assets[].size`, `assets[].state` (`uploaded` হলে দেখাও), `assets[].browser_download_url`। হেডার `If-None-Match: <আগের ETag>` পাঠালে না বদলালে `304` আসে (লিমিটে গোনা হয় না)। লিমিট: টোকেন ছাড়া প্রতি IP ঘণ্টায় ৬০।

নিয়ম:
- `Bangla__...` → বাংলা ট্যাব, `Original__...` → মূল কিতাব ট্যাব
- `^(.+?)_part(\d+)of(\d+)\.pdf$` মিললে একই base-এর সব পার্ট মিলে এক কিতাব

### `catalog.json` (`https://raw.githubusercontent.com/Arifmullikh/qawmi-kitab/main/catalog.json`)
উপরের সব কিছু একসাথে, আগেই হিসাব করা:
```jsonc
{
  "schema": 1,
  "repo": "Arifmullikh/qawmi-kitab",
  "generated_at": "2026-11-20T06:00:00Z",
  "total_files": 536, "total_size": 20000000000,
  "groups": { "marhala": "...", "takhassus": "..." },
  "jamats": [
    {
      "order": 1, "tag": "taisir", "name_bn": "তাইসীর", "name_en": "Taisir", "group": "marhala",
      "release_url": "https://github.com/Arifmullikh/qawmi-kitab/releases/tag/taisir",
      "book_count": 20,
      "books": [
        {
          "id": "taisir/Bangla__14_Beheshti-Gauhar_Bangla.pdf",
          "section": "bangla",            // "bangla" | "original"
          "title": "বেহেশতী গাওহার",
          "lang": "bn",                   // bn | ar | ur | fa | null
          "size": 4921536,                // সব পার্ট মিলিয়ে বাইট
          "parts": [
            { "name": "Bangla__14_Beheshti-Gauhar_Bangla.pdf", "part": 1, "size": 4921536,
              "url": "https://github.com/Arifmullikh/qawmi-kitab/releases/download/taisir/Bangla__14_Beheshti-Gauhar_Bangla.pdf",
              "updated_at": "..." }
          ]
        }
      ]
    }
  ]
}
```
raw.githubusercontent.com প্রায় ৫ মিনিট ক্যাশ রাখে, আর Action ৩০ মিনিট পরপর (রিলিজ এডিট করলে সাথে সাথে) চলে। তাই সবচেয়ে তাজা তালিকার জন্য Releases API, আর ব্যাকআপ হিসেবে catalog.json ব্যবহার করো।
