const fs = require('fs');
const path = require('path');

const screens = [
  {
    order: 1,
    id: "7934ec344e8d4c1485952f71ef987dbe",
    title: "Login (Final Refinement)",
    slug: "01_login",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1WyAoT7u1PiWE69pGxhNfMU_qAKdhdY6xTLbBbk0qBWZXEEeUFyT9r1_Jprw6pl7MsjWprF-gD-zOLbeEF8NTH8QS_aviexmunPBqt25hrPrxBoQC4ohJx9LKlwkGUbUvVPovEUkrkoYDizr18PSfOGfnKiFpK3whZMOc4Bi6YN1Hk5bYAq8cdrFauId2_GZty_9zEpOtJyv5m21YpJo5Ic2rPdTO_ihyjTF-LUX_uwfgXRy9tFJtySTKk",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkODFmZjg3ODYwMWI0ZTFiMTRmMDg4NTZlEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 2,
    id: "e7965523386c4356b6fb602ca26bcc31",
    title: "Dashboard (Standardized Nav)",
    slug: "02_dashboard",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1VJmsLCak7ATpvSHnoqDKIBUe1YIDOlsM0xIw_uMkz7Zy0Iw6hPEEN-5wZ2sRpYdZVe78YbEozeGocAp75h5Ale7xbKByOy6zSKWriQp6mYbi_LCpmkb4Fj_WHz7t99WAaH2gEXD5yhhEZq0gR4ZIidel_8E_SHzYTfIj_CZ-_7GevIJSEM0L1G_k09PyNEifh3j1ExTOX7xvwZGqvubOP2tlc5xSIXEQ3M3U8OEnjgs4LiouZeLeUqQ70",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTE0OWRlNDZkZWMwMWE2MTEwMDk4MDc0MDIyEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 3,
    id: "43e55e4d779c4c0ba60b7e4885258c8d",
    title: "Extracted Declarations (Final)",
    slug: "03_extracted_declarations",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1W7wvw6JgTXgZgiEumDHD4W7MTORV3KJd_WyI4hKkVGVGwnf339tfjXwO-PqT2bR3EFKyIPc-6NqF6gYtGiYwrszfPSQzHFYSuUxyvXbY0ctWu-LQtHCZTuPNPwdh4RTKfCB2nxy3lkK3LfKyWrWzyk66tPBNSspkzxNeEUR60PACTxX_rBtmDYeqmlvwXMUQI9EV-XQNpgcVqt6a9zB70742G2a2EjCCp1d-xxjOfdtIn74-wHOAt8924",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTE1MDY4NTZkOTIwMmE5YjZjNzlmMGI1OWZiEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 4,
    id: "764b68d7afaf4473b06fb25868a0ba2e",
    title: "New Inspection - Step 1 (Final)",
    slug: "04_new_inspection_step1",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1UYDm-r4rUsN5osFUHM6NgNS7u3IcRZjW25BBbUVQBlMLpM_iZ6sd3W_J6I4QJdc4mggl-G1FjRuhlYwRirClBK3nekKLS2a8G9XgKm-iB_xbE9KrKmcZEAeAwqUActrnB5-VVoAAt7N7__Fxp1S6sS7nyT4CrTYHWGRCRkbmwvQLY44tBurQNT4dmZSlW8S8ZICAkd85baio9FiYSzZphoWSQBDh7ETU5eV0MQZCu3hu5CSnVyU_lRO1k",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkODI1MzEyY2IwNzNhZDZhYWQxMTJlY2JiEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 5,
    id: "e87597a62bc94b0f898ded1ae4dcd8b5",
    title: "Findings (Final Refinement)",
    slug: "05_findings",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1U0qVWn6JnYSr2GJ0qPKISWWSUkc24iKbG9J-Nk-444PHbf7wWND67aHlfKTWD2wqqnJL-en9Zdo48mzgGYlwVM56uA8kjWUtrrtxbnBLDc9cfjZs4S4fWmo6nf5hfSBRvjGrTFd11kCbIfWN9c1_9e1ByYiJsEajHV3OXzv-hbVkTEaz7dhx6zlKCD7ajjVxHXji3ppaEZ3hg6-wHG0ZVvGzJWdRN92WI60ZYBuN1qckYXiaRg7GOINJ8",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTE1MzEwNDZmYTQwNzA5MmNlNWMyMGU2Y2E4EgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 6,
    id: "c15bb16335bb4f28a67e055cbae216cc",
    title: "Evidence Review (Final Polish)",
    slug: "06_evidence_review",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1UABObTqwF9T8Y0O3yjEe0vJfzSLPpfNe6cZJb75_u-czuN2a-J_3bcTFQLpEQl_n-jdEwWKUqLn6pz5H9C93u23_tWC2iW___XeHYESRxz4QjeKJBSznzdyuE8n6K776KoR8ox8RxCcIpQhTPljwxPTc8g5mqEt3Q4SeZKZyAyublYXaQrBWWA3pfOsztbOB-o81YwnXBNEP5hZKpU6hnhI1vhGMfkXVpbcXaRnKWy4NOC3j0lsaE7y6U",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkYzg1NTMwM2MwN2M0ZTYyODUxMzAzYjdhEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 7,
    id: "1a1f4dfa11fb4c668905f736c4e55751",
    title: "Inspection Report Preview (Final Polish)",
    slug: "07_inspection_report_preview",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1Xb4XTfk4Ff-QGdbar2cChgrAMpMsTXAJ2n965PMPvm1o6fIqG-5L1OxatykF6eykPMbX5T841pMuvhRUAmqjRSyZPik_Ql_PkVkSHPF1z5Jk9-nKV2BiD1MmmT-dsrSovXndWQAGhfOztg4yHOP7HAoWQEjlbNXSXUQh4VVNjQlQKOCMK6EVS-UhktIQk-K1RpBqF2V6PDPUwbIPUAxkZWDzqsNdx5nFlq6fKroyvJcuKUcqmbnSjNCQ",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTE1MjIxZDI4ODUwNTc2MDE4NzNlMTAyNGRiEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 8,
    id: "da1a0aa73c734df290ed9b86e988458c",
    title: "Reports List (Final Polish)",
    slug: "08_reports_list",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1WQ7vgWQI1e3IX3SjL22zRCDuld3KllyJ0TaqIM9NHcCDL97Xc-1KZmM7CPqpHMKrx_vm5jkDwDbg_r7qOIomhxzfDLQKQcPqIt63esvDkiaI9nvocLHStPbMhcKBLF_RKaKe5PSm5OZJPa2vsnHIF-tm7q9KHduVD9aOQH1XfRIjpnhv0-K55nmaH-GqThpb3uOaSrjRHSll40wlFlkUn08hb4ZspJsx68YhDmMEUpKlmHzpEqSRL0T7g",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTE0OWUwYjY2Y2EwMmQzZDE5OWJiMTE0NjNhEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 9,
    id: "9c1ea2d011c54661b541e5d371e8c4ab",
    title: "Capture Images (Quality Warning State)",
    slug: "09_capture_images_warning",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1WAD7b1PylKr6tYdI88rok3tCktztt7xkQ-IEuxPTGU8Fg47PVqP4URYuhiqousvORh-cmCqLRXZuNHgFjQeTDs-IG1fdUn2zL1APUyGeXEZtANUKCwt-9pp6AbXXUyl4OPdR95k_oQM4vR8urInM8bSeAfVKLeaoj3fnFs9HmdeIJQ8BEvVf1uwxl8jNzlA7mI1cT7ZpXfWq1qhHvebwid0KF2utk-PURMiTpArYXRA-MN5A5jVeyp9-Q",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkZjMwYzQ1OWUwNzc5OWVmYWVkMDhlNzEyEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 10,
    id: "68c6206e848449a5b8d69d94ba97e50d",
    title: "Profile (Final)",
    slug: "10_profile",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1UR2rZ4tmlA9k-8whkpNnnBjRYdLSDNU84m4XjvSWjemtHwfJ9o-KULMADZ2H7ONaVXRHF0UdVRYSFXK-p07C4gI6fCmBJBineNKxdjKWcoAABWp8COXmo9MDCJbw_ZxLJJ78iX59rIXl11NzI6vJzyYeJEjpQbkKXu4ITzwXpFKWYAGZFu0ePZqGHavEmGmL4Nx00ZfLw-bT8GXXdRf-UFEHOf2bXsQTxJHSoSDgjDivPY9p2BtP0IIOs",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkZjJjMDBlOWEwNzA5MmIzMDhjMDFlNjkxEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 11,
    id: "a81ca27561c4472b9cdec2e3b426f870",
    title: "Draft Saved / Offline State",
    slug: "11_draft_saved_offline",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1UZoEeLWJb3AEugAHbHNMxf9EtR-8bEw1vKgspRvqQhvkyo-HXGZEWvNCBrF6yGa35AUQsyDfHrEGGKybnu-9Aj-D5Xu2QptmdXBCREVF9vYnvgXe9l89YKUPBI-7SuZyBKj4ZxHr67Sr3h7WpHpjAsWqZQf3hPbNarN_EP3SbLXGYHE5G-r_Ao7HIZBa360t0D4h0q2Da25sfbUyrFcepIftdVhVcLD-cEY19k83VxREoQL9JAe4BOspY",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkY2EyYjRjMTgwMjJkNGE1MGMzMDI3N2M1EgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 12,
    id: "c06a66b25de1406a8812ef0bd80539a4",
    title: "Analyzing...",
    slug: "12_analyzing",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1WBSPhKKssJFtXwmqVevqU7UWiR1rdYUYR8SlIScIuzy6SSdFGqKiMxXvJ4dwecMDrSGf4AaMCq_5jW5duweQkxCcFKtxYSL3EFnnLr6tiea5F-8Pb016q_-Qffu0LhsCxiIOYa4rBhJvO1bsIj3ziJTLJn9WOITGNYKOzrQavhn7bDQcJMyriMolqqhhVADzvUa30S6MG_NUH4j_rnOUeygfOKsLMAPddd9mATqmyc86uGqXnFwcRoPtM",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBjODQ2YTA4ODMwMDMwM2UwMjZkMmNjMTVhEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  },
  {
    order: 13,
    id: "74f01d043845446297bf2569fafb8035",
    title: "Step 3 of 3: Review & Submit",
    slug: "13_step3_review_and_submit",
    screenshotUrl: "https://lh3.googleusercontent.com/aida/AEtjO1VVbrQTRZhrb_q6wwkKdfX5deMm4g_OGQLCG4GfSKFDgHwQQ0l-BV48v7eas2zmXsIeFugtugYUxYJCK6MV38w62oC0RnM1Rmhp6XhbdArYaiv8JzDsRkxJe6SlcLbLrQMHSelqqBz1Eq4G9QMbQmoO8jlCas35MkLHg18bxtPnBTPDfIEcCvggil_Jz-aW_EDuQjskRZ5CqIR2DSLO2Dplz-DqIXTqkNetUMeiLcRu8PM0Raj8tdn_94Q",
    htmlUrl: "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzAwMDY1YTBkY2E1YmFmMzIwN2M0Y2E1ODdiMTE0NWQyEgsSBxD39OO_ihkYAZIBIwoKcHJvamVjdF9pZBIVQhMzMjc3NjYzMjY2OTc4NTcyMjU3&filename=&opi=89354086"
  }
];

const targetDir = path.join(__dirname, 'stitch_screens');
const imagesDir = path.join(targetDir, 'images');
const codeDir = path.join(targetDir, 'code');

fs.mkdirSync(imagesDir, { recursive: true });
fs.mkdirSync(codeDir, { recursive: true });

async function downloadFile(url, destPath) {
  const res = await fetch(url, { redirect: 'follow' });
  if (!res.ok) {
    throw new Error(`Failed to download ${url}: ${res.status} ${res.statusText}`);
  }
  const arrayBuffer = await res.arrayBuffer();
  fs.writeFileSync(destPath, Buffer.from(arrayBuffer));
}

async function main() {
  console.log(`Starting download of ${screens.length} screens...`);
  const manifest = [];

  for (const s of screens) {
    console.log(`[${s.order}/${screens.length}] Downloading: ${s.title} (${s.id})`);
    
    const imgFilename = `${s.slug}.png`;
    const htmlFilename = `${s.slug}.html`;
    
    const imgPath = path.join(imagesDir, imgFilename);
    const htmlPath = path.join(codeDir, htmlFilename);

    try {
      await downloadFile(s.screenshotUrl, imgPath);
      console.log(`  -> Saved image: ${imgFilename}`);
    } catch (err) {
      console.error(`  -> Error downloading image for ${s.title}:`, err.message);
    }

    try {
      await downloadFile(s.htmlUrl, htmlPath);
      console.log(`  -> Saved code: ${htmlFilename}`);
    } catch (err) {
      console.error(`  -> Error downloading code for ${s.title}:`, err.message);
    }

    manifest.push({
      order: s.order,
      id: s.id,
      title: s.title,
      imageFile: path.relative(targetDir, imgPath).replace(/\\/g, '/'),
      codeFile: path.relative(targetDir, htmlPath).replace(/\\/g, '/'),
      screenshotUrl: s.screenshotUrl,
      htmlUrl: s.htmlUrl
    });
  }

  fs.writeFileSync(
    path.join(targetDir, 'manifest.json'),
    JSON.stringify({ projectId: "3277663266978572257", projectTitle: "Legal Metrology Field Inspect", screens: manifest }, null, 2)
  );

  console.log(`\nAll screens downloaded successfully into: ${targetDir}`);
}

main().catch(err => {
  console.error("Fatal error:", err);
  process.exit(1);
});
