create table if not exists demo_user (
    id bigserial primary key,
    name varchar(100) not null,
    phone varchar(32) not null,
    created_at timestamp with time zone not null default now(),
    constraint uk_user_phone unique (phone)
);
