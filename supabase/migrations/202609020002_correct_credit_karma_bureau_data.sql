-- Draft only: run manually in the standalone Supabase project after review.
-- Source checked 2026-09-02:
-- https://www.creditkarma.ca/credit/i/equifax-vs-credit-karma-whats-the-difference
-- Credit Karma Canada states that it works with TransUnion and provides a
-- TransUnion credit score and report, updated weekly. It does not provide both
-- Equifax and TransUnion data in Canada.

update public.financial_tools
set
  tagline =
    'Free TransUnion credit score and report access, weekly updates, and matched product offers.',
  description =
    'Credit Karma is a free financial platform that gives Canadians access to their TransUnion credit score and credit report, with weekly updates. It also shows matched credit card and personal loan offers based on a member''s credit profile. Credit Karma is not a credit bureau and does not calculate the score; it displays information supplied by TransUnion. The platform earns money when members apply for products through its links, so its matched offers are a starting point for independent research rather than a complete view of the market.',
  key_features = array[
    'Free TransUnion credit score',
    'Weekly TransUnion credit updates',
    'TransUnion credit report access',
    'Matched credit card and loan offers',
    'Credit education resources'
  ]::text[],
  embedding = null,
  updated_at = now()
where id = 'da0bd0e0-f7b7-4b16-bb65-243205ba1cf4';
