# কওমি কিতাব (Qawmi Kitab) — লাইভ API

কওমি মাদরাসার জামাতভিত্তিক সিলেবাসের কিতাবের PDF (বাংলা + মূল আরবি/উর্দু/ফারসি)। **An Nur** অ্যাপের "কওমি কিতাব" অংশ এই রিপো থেকে সরাসরি তালিকা ও PDF টানে। এখানে কিতাব যোগ/মুছলে অ্যাপে নিজে থেকেই আপডেট হয় — **অ্যাপ আপডেট লাগে না**।

## কীভাবে সাজানো

| জিনিস | কোথায় | কাজ |
|---|---|---|
| প্রতিটা জামাতের ফোল্ডার | [Releases](https://github.com/Arifmullikh/qawmi-kitab/releases) — প্রতি জামাতে একটা রিলিজ | PDF ফাইলগুলো রিলিজের asset হিসেবে থাকে |
| `jamats.json` | রিপোর রুটে | জামাতের ক্রম, বাংলা নাম, গ্রুপ (মারহালা / তাখাসসুস) |
| `names.json` | রিপোর রুটে | প্রতিটা ফাইলের বাংলা নাম ও ভাষা |
| `catalog.json` | রিপোর রুটে (অটো তৈরি) | সব জামাত + সব কিতাব + সাইজ + ডাউনলোড লিংক এক ফাইলে |

রিলিজ ট্যাগ (জামাতের ক্রমে): `taisir`, `mizan`, `nahbemir`, `hedayatun-nahu`, `kafiya`, `sharhe-jami`, `sharhe-bekaya`, `jalalain`, `mishkat`, `dawra`, `takhassus-ifta`, `takhassus-hadith`, `takhassus-tafsir`, `takhassus-fiqh`, `takhassus-adab`, `takhassus-qiraat`, `takhassus-dawah`

## অ্যাপ যেসব লিংক থেকে ডেটা নেয়

- এক ফাইলে সব (সবচেয়ে সহজ, রেট লিমিট নেই): `https://raw.githubusercontent.com/Arifmullikh/qawmi-kitab/main/catalog.json`
- লাইভ তালিকা (সাথে সাথে আপডেট): `https://api.github.com/repos/Arifmullikh/qawmi-kitab/releases?per_page=100`
- জামাতের তালিকা: `https://raw.githubusercontent.com/Arifmullikh/qawmi-kitab/main/jamats.json`
- বাংলা নাম: `https://raw.githubusercontent.com/Arifmullikh/qawmi-kitab/main/names.json`
- PDF ডাউনলোড: `https://github.com/Arifmullikh/qawmi-kitab/releases/download/<tag>/<ফাইলের-নাম>.pdf`

টোকেন লাগে না (রিপো পাবলিক)। GitHub API টোকেন ছাড়া প্রতি ডিভাইসে ঘণ্টায় ৬০ বার কল করা যায়, তাই অ্যাপ ক্যাশ রাখে আর `catalog.json` ব্যাকআপ হিসেবে ব্যবহার করে।

## কিতাব যোগ করা (GitHub ওয়েবসাইট থেকে)

1. [Releases](https://github.com/Arifmullikh/qawmi-kitab/releases) পেজে যাও, যে জামাতে যোগ করবে সেই রিলিজ খোলো।
2. ডানে ✏️ **Edit** চাপো।
3. নিচে **"Attach binaries by dropping them here"** ঘরে PDF টেনে এনে ছাড়ো (একেকটা ফাইল ২ GB পর্যন্ত)।
4. আপলোড শেষ হলে **Update release** চাপো। ব্যস — অ্যাপে চলে আসবে।

## কিতাব মুছে ফেলা

রিলিজ → ✏️ **Edit** → যে ফাইল মুছবে তার পাশে 🗑️ → **Update release**।

## ফাইলের নামের নিয়ম (জরুরি)

GitHub ফাইলের নামে বাংলা/আরবি অক্ষর নষ্ট করে ফেলে, তাই নামে **শুধু ইংরেজি অক্ষর, সংখ্যা, `-` আর `_`** রাখো:

- বাংলা অনুবাদ/শরাহ: `Bangla__Kitaber-Naam.pdf` → অ্যাপে "বাংলা" ট্যাবে দেখাবে
- মূল ভাষা: `Original__Kitaber-Naam.pdf` → অ্যাপে "মূল কিতাব" ট্যাবে দেখাবে
- খণ্ড আলাদা বই হলে: `Original__Fathul-Bari-Vol-01.pdf`, `...-Vol-02.pdf` (প্রতিটা আলাদা কিতাব হিসেবে দেখাবে)
- একটা বই কয়েক ভাগে কাটা হলে: `Original__Kitab_part01of03.pdf`, `..._part02of03.pdf` → অ্যাপে **এক কিতাব** হিসেবে দেখাবে

## বাংলা নাম দেওয়া (ঐচ্ছিক)

`names.json` খুলে ✏️ চাপো, এরকম একটা লাইন যোগ করো, তারপর **Commit changes**:

```json
"mizan/Bangla__Kitaber-Naam.pdf": {"title": "কিতাবের বাংলা নাম", "lang": "bn"},
```

`lang`: `bn` বাংলা, `ar` আরবি, `ur` উর্দু, `fa` ফারসি। নাম না দিলে অ্যাপ ফাইলের নাম থেকেই একটা নাম বানিয়ে দেখাবে।

## নতুন জামাত যোগ করা

1. নতুন রিলিজ বানাও (Releases → **Draft a new release** → নতুন ট্যাগ, যেমন `takhassus-new`, টাইটেল বাংলায়) → **Publish**।
2. `jamats.json`-এ ওই ট্যাগ, বাংলা নাম আর গ্রুপ যোগ করো (ক্রম ঠিক করতে)। না করলেও অ্যাপ তালিকার শেষে দেখাবে।

## catalog.json কীভাবে আপডেট হয়

`.github/workflows/catalog.yml` অ্যাকশন রিলিজ এডিট/পাবলিশ হলে, `names.json`/`jamats.json` বদলালে, আর প্রতি ৩০ মিনিটে নিজে নিজে `catalog.json` নতুন করে বানায়। হাতে চালাতে: Actions → **Update catalog.json** → **Run workflow**।

---
⚠️ কিছু বাংলা অনুবাদ/শরাহ প্রকাশনীর কপিরাইটভুক্ত হতে পারে। কোনো প্রকাশনী আপত্তি জানালে সংশ্লিষ্ট ফাইল সরিয়ে দিন।
