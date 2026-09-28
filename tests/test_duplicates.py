import json

from scrapy.http import HtmlResponse, Request

from polite_crawler.fingerprints import NearDuplicates, content_hash, simhash
from polite_crawler.spiders.site import SiteSpider

# About 200 words each. Hamming <= 3 bits marks pages about 97% alike or more: on short
# texts one changed word is already more than that.
ARTICLE = (
    "Repot a plant in spring when roots start to circle the bottom of its pot or grow out of the drainage holes. "
    "Choose a new pot only one size larger, because too much wet compost around a small root ball causes rot. "
    "Water the plant the day before. Tip it out gently, loosen the outer roots with your fingers, and set it at "
    "the same depth it grew before. Fill around it with fresh compost, firm it lightly, and water until it drains. "
    "Keep the plant out of direct sun for a week while the roots settle into their new home. We started the shop "
    "in a rented greenhouse with forty cuttings and a secondhand heater. Today three growers look after about two "
    "thousand plants, and we still pot every one of them by hand. We do not use peat, we reuse every pot that "
    "customers bring back, and our delivery vans run on electricity. A Boston fern likes steady humidity and bright "
    "shade, so a bathroom window suits it well. A snake plant survives low light and forgotten watering, with stiff "
    "upright leaves and yellow edges. A peace lily flowers in spring, droops when thirsty and recovers within an hour "
    "of water. A spider plant sends out runners with baby plants that root in a glass of water on the windowsill."
)
OTHER = (
    "More house plants die from too much water than from too little. Push a finger into the compost: if the top "
    "two centimetres are dry, water thoroughly; if they are damp, wait a few days and check again. Plants grow "
    "slowly in winter and need far less water, even though central heating dries the air. In summer check them "
    "twice a week, and move pots away from hot windows during the afternoon. Use water at room temperature, and "
    "empty the saucer half an hour after watering. A rubber plant has glossy dark leaves; wipe them with a damp "
    "cloth once a month. Pothos has trailing stems for high shelves, so cut it back to keep it bushy. A zebra plant "
    "has striped leaves and a yellow flower spike and needs rain water or filtered water. Calathea leaves fold up "
    "at night; keep it away from cold draughts and radiators. A jade plant is a slow succulent that can live for "
    "decades with very little care. A monstera grows split leaves as it matures, so give it a moss pole to climb. "
    "A parlour palm has soft fronds, is happy in a dim corner, and is safe around cats and dogs in the house."
)


LONG = ARTICLE + " " + OTHER  # 425 words
UPDATED = LONG + " Last updated on 3 May 2026."  # the same page with a date line added


def test_fingerprints():
    assert content_hash(ARTICLE) == content_hash("  " + ARTICLE.upper().replace(" ", "\n"))  # case and spacing
    assert content_hash(ARTICLE) != content_hash(UPDATED)
    assert content_hash("too short to judge") is None and simhash("too short to judge") is None
    assert (simhash(LONG) ^ simhash(UPDATED)).bit_count() <= 3
    assert (simhash(LONG) ^ simhash(LONG.replace("fresh compost", "new compost"))).bit_count() <= 3
    assert (simhash(ARTICLE) ^ simhash(OTHER)).bit_count() > 10

    index = NearDuplicates()
    index.add(simhash(LONG), "https://x.test/a")
    assert index.find(simhash(UPDATED)) == "https://x.test/a"
    assert index.find(simhash(OTHER)) is None
    # Up to 3 differing bits fall in at most 3 of the 4 bands, so one band always matches;
    # 4 bits spread over all four bands are not a near-duplicate.
    base = simhash(LONG)
    assert index.find(base ^ (1 | 1 << 16 | 1 << 32)) == "https://x.test/a"
    assert index.find(base ^ (1 | 1 << 16 | 1 << 32 | 1 << 48)) is None


def page(spider, path, text, links=""):
    url = f"https://example.com{path}"
    body = f"<html><body><article><p>{text}</p></article>{links}</body></html>".encode()
    out = list(spider.parse(HtmlResponse(url, body=body, request=Request(url))))
    return out[0], [r.url for r in out if isinstance(r, Request)]


def test_spider_marks_duplicates_and_does_not_follow_copies(tmp_path):
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    first, _ = page(spider, "/guide", LONG)
    assert first["content_hash"] and first["duplicate_of"] is None and first["near_duplicate_of"] is None

    copy, followed = page(spider, "/print/guide", LONG, '<a href="/more">more</a>')
    assert copy["duplicate_of"] == "https://example.com/guide" and copy["content_hash"] == first["content_hash"]
    assert followed == []  # nothing new behind an exact copy

    near, followed = page(spider, "/guide-2026", UPDATED, '<a href="/more">more</a>')
    assert near["near_duplicate_of"] == "https://example.com/guide" and near["duplicate_of"] is None
    assert followed == ["https://example.com/more"]  # a near-duplicate is only marked

    other, _ = page(spider, "/watering", OTHER)
    assert other["duplicate_of"] is None and other["near_duplicate_of"] is None
    short, _ = page(spider, "/short", "Call us.")
    assert short["content_hash"] is None and short["simhash"] is None
    gone = "https://example.com/gone"
    missing = list(spider.parse(HtmlResponse(gone, status=404, body=f"<p>{LONG}</p>".encode(), request=Request(gone))))[0]
    assert missing["content_hash"] is None  # error pages are not fingerprinted


def test_resume_rebuilds_fingerprints(tmp_path):
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    rows = [page(spider, "/guide", LONG)[0], page(spider, "/watering", OTHER)[0]]
    (tmp_path / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    resumed = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    assert resumed.rows == 2
    copy, _ = page(resumed, "/print/guide", LONG)
    assert copy["duplicate_of"] == "https://example.com/guide"
    near, _ = page(resumed, "/guide-2026", UPDATED)
    assert near["near_duplicate_of"] == "https://example.com/guide"
