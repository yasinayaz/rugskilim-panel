-- Satılan ürünlere kargo takip numarası alanı.
-- Mevcut products tablosuna kolonu idempotent şekilde ekler.
-- Supabase SQL Editor'de bir kez çalıştırın.

alter table public.products
  add column if not exists shipping_tracking_no text;
