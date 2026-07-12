-- Satılan ürünlere kargo bilgisi (tek gönderi; firma + TL + USD tutarı).
-- Mevcut products tablosuna kolonları idempotent şekilde ekler.
-- Supabase SQL Editor'de bir kez çalıştırın.

alter table public.products
  add column if not exists shipping_carrier text,
  add column if not exists shipping_cost_try text,
  add column if not exists shipping_cost_usd text;
