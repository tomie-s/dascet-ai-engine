-- Draft only: run manually in the standalone Supabase project after review.
-- Source checked 2026-09-02:
-- https://helpcentre.trading212.com/hc/en-us/articles/12933782261917-What-are-the-supported-countries
-- Canada is absent from the supported-country list, and the page states that
-- Trading 212 information is not directed at residents of Canada.

update public.financial_tools
set
  canadian_available = false,
  canadian_available_notes =
    'Not available to Canadian residents according to Trading 212''s supported-country list checked 2026-09-02.',
  description =
    'Trading212 is a commission-free investing platform offering stocks, ETFs, CFDs, fractional shares, automated portfolio allocation through Pies, and a practice account. It is not available to Canadian residents and does not offer Canadian registered accounts such as TFSAs, RRSPs, or FHSAs.',
  embedding = null,
  updated_at = now()
where id = '8f5e03c1-0570-4699-a9ca-41f26fbbbb1f';
