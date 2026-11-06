"""The default presentation page `init` scaffolds, as one string.

Data, not logic: nothing in this file runs. Kept inline rather than vendored
as an .html file so the engine stays hermetic. NAV and STATS are the
marker-delimited regions the engine rewrites; everything else is authored
prose the user (or the skill) replaces. Callers fill %%REPO_NAME%% and
%%REPO_URL%% with str.replace, not str.format: the CSS has literal braces.
"""
# implements: ARCH-SITE-026
SITE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%REPO_NAME%% - project site</title>
<!--
  Regions between <!##REQMAP:...##> markers are rewritten by
  `reqmap.py sync` on every run. Everything else is authored and preserved.
-->
<style>
  /*##TOKENS:SITE##*/
  :root{
    --paper:#f2ead8; --card:#fdf8ed; --ink:#24201a; --muted:#6d6554;
    --line:#dcd2b8; --accent:#0d64c8;
    --radius:12px; --maxw:980px;
  }
  @media (prefers-color-scheme: dark){:root{
    --paper:#17140f; --card:#26211a; --ink:#f3ede0; --muted:#9d9482;
    --line:#3a3427; --accent:#3d92f5;
  }}
  /*##/TOKENS:SITE##*/
  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink);
       font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,
       sans-serif; line-height:1.55}
  a{color:inherit}
  .wrap{max-width:var(--maxw); margin:0 auto; padding:0 16px}
  .nav{position:sticky; top:0; background:var(--paper);
       border-bottom:1px solid var(--line)}
  .nav-inner{max-width:var(--maxw); margin:0 auto; padding:12px 16px;
             display:flex; align-items:center;
             justify-content:space-between; gap:16px}
  .brand{font-weight:700}
  .nav-links{display:flex; gap:6px; flex-wrap:wrap}
  .nav-links a{text-decoration:none; font-weight:600; padding:6px 10px;
               border-radius:8px; border:1px solid transparent}
  .nav-links a:hover{border-color:var(--line); color:var(--accent)}
  section{padding:48px 0; border-bottom:1px solid var(--line)}
  h1{font-size:clamp(2rem,5vw,3rem); line-height:1.1; margin:.2em 0}
  h2{margin:0 0 .4em}
  .lead{font-size:1.1rem; color:var(--muted); max-width:60ch}
  .stats{display:grid; gap:12px; margin-top:8px;
         grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
  .stat{background:var(--card); border:1px solid var(--line);
        border-radius:var(--radius); padding:14px; text-align:center}
  .stat b{display:block; font-size:1.6rem; font-weight:800}
  .stat span{font-size:.74rem; color:var(--muted);
             text-transform:uppercase; letter-spacing:.04em}
  .src{font-size:.8rem; color:var(--muted)}
  code{font-family:ui-monospace,Menlo,Consolas,monospace}
</style>
</head>
<body>
<div class="nav">
  <div class="nav-inner">
    <div class="brand">%%REPO_NAME%%</div>
    <!--##REQMAP:NAV##--><!--##/REQMAP:NAV##-->
  </div>
</div>
<section>
  <div class="wrap">
  <!-- author me -->
    <h1>%%REPO_NAME%%</h1>
    <p class="lead">Replace this paragraph with what the project does and
      why. The engine never touches it.</p>
    <p><a href="%%REPO_URL%%" target="_blank" rel="noopener">Source</a></p>
  </div>
</section>
<section>
  <div class="wrap">
    <h2>The requirements, right now</h2>
    <div class="stats">
      <!--##REQMAP:STATS##--><!--##/REQMAP:STATS##-->
    </div>
    <p class="src">Counted from the requirement graph by
      <code>reqmap.py sync</code> on every run.</p>
  </div>
</section>
</body>
</html>
"""
