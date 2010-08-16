So far this just includes a log parser, and it only works with MySQL.

Install
-------

Create a database/user called "minecraft". If you want to use another value, modify parser as
you see fit. Once created, run the following:

    mysql -uminecraft -Dminecraft < sql/visitors.sql

Now pop open a screen session, via `screen -s mclog`. Since the script isn't daemonized this will
keep it running after you close your terminal.

To start the log parser, use the following:

    python parser.py /home/minecraft/server.log

Obviously replace the path with the precise path to your servers log.

Usage
-----

Some sample queries, which we use on the Nibbits Minecraft site can be seen below.

Online members, sorted by duration online:

    select name, unix_timestamp(now()) - unix_timestamp(date_joined) as duration
    from mc_visitor
    where date_left is null
    order by duration desc;

All visitors, sorted by time played:

    select name, count(*) as num, sum(unix_timestamp(ifnull(date_left, now())) - unix_timestamp(date_joined)) as duration,
      max(date_joined) as last_seen, min(date_joined) as first_seen
    from mc_visitor
    group by name
    having duration > 5
    order by duration desc, name