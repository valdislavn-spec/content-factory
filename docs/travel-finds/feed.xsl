<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="html" encoding="UTF-8" indent="yes"/>
<xsl:template match="/rss/channel">
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title><xsl:value-of select="title"/></title>
<style>
body{margin:0;background:#f5f7fb;color:#14181f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;line-height:1.55}
.wrap{max-width:760px;margin:0 auto;padding:28px 20px 56px}
h1{font-size:24px;margin:0 0 4px}.sub{color:#5c6470;font-size:14px;margin:0 0 24px}
a{color:#1857e6}.item{background:#fff;border:1px solid #e4e8f0;border-radius:14px;padding:18px 20px;margin:0 0 14px}
.item h2{font-size:18px;margin:0 0 6px}.item h2 a{text-decoration:none}
.item time{color:#7a8290;font-size:13px}.item p{margin:8px 0 0;color:#3a424e;font-size:15px}
.note{margin-top:22px;font-size:12.5px;color:#7a8290}
.note a{color:#7a8290}
</style></head><body><div class="wrap">
<h1><xsl:value-of select="title"/></h1>
<p class="sub"><xsl:value-of select="description"/></p>
<xsl:for-each select="item">
<div class="item">
<h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
<time><xsl:value-of select="pubDate"/></time>
<p><xsl:value-of select="description"/></p>
</div>
</xsl:for-each>
<p class="note">RSS 2.0 feed · <a href="https://valdislavn-spec.github.io/content-factory/travel-finds/">Travel Finds</a></p>
</div></body></html>
</xsl:template>
</xsl:stylesheet>
