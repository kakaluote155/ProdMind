insert into demo_user(name, phone)
values ('Existing User', '13800000000')
on conflict (phone) do nothing;
