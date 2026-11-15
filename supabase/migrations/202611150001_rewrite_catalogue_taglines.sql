-- Draft only: run manually in the standalone Supabase project after review.
-- Phase 6, task 4: catalogue tagline rewrites, tested with npm run eval:whatif before this
-- change (see evals/catalogue_rewrites.json and EVALUATION.md section 4). Each rewrite only
-- rephrases facts already in the product's row. Clearing the embedding lets
-- experiments/02-embed-all-tools.ts re-embed these rows, and only these rows.
-- Each update matches the old tagline, so it changes nothing if run twice or on a changed row.

-- Credit Counselling Society: targets debt-02, mt-01, debt-04
update public.financial_tools
set
  tagline = 'Non-profit Canadian credit counselling for paying down debt, with a Debt Management Program that consolidates unsecured debts and can reduce interest.',
  embedding = null,
  updated_at = now()
where id = 'a362a427-492b-40e0-9b1e-20a5ee90660d'
  and tagline = 'Non-profit Canadian credit counselling service for debt help and money management.';

-- BMO Savings Builder Account: targets sav-03
update public.financial_tools
set
  tagline = 'BMO savings account that pays bonus interest for regular monthly deposits, to help build a steady savings habit.',
  embedding = null,
  updated_at = now()
where id = 'eca1cdc1-2ec5-4670-910f-6095e5946f0d'
  and tagline = 'BMO savings account designed to reward ongoing savings habits inside BMO banking.';

-- Rollback (run manually, then re-run experiments/02-embed-all-tools.ts):
--
-- update public.financial_tools
-- set tagline = 'Non-profit Canadian credit counselling service for debt help and money management.', embedding = null, updated_at = now()
-- where id = 'a362a427-492b-40e0-9b1e-20a5ee90660d';
--
-- update public.financial_tools
-- set tagline = 'BMO savings account designed to reward ongoing savings habits inside BMO banking.', embedding = null, updated_at = now()
-- where id = 'eca1cdc1-2ec5-4670-910f-6095e5946f0d';
