create table mc_visitor (
    id int primary key auto_increment,
    server_id int default 1,
    name varchar(64),
    ip varchar(32) null,
    date_joined datetime,
    date_left datetime null
);
create index name on mc_visitor (server_id, name);
create unique index name_date on mc_visitor (server_id, name, date_joined);