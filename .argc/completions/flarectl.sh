#!/usr/bin/env bash
# Automatic generated, DON'T MODIFY IT.

# @option --account-id <value>    Optional account ID [$CF_ACCOUNT_ID]
# @flag --json                    show output as JSON instead of as a table (default: false)
# @flag -h --help                 show help
# @flag -v --version              print the version

# {{ flarectl dev
# @cmd
dev() {
    :;
}
# }} flarectl dev

# {{ flarectl ips
# @cmd Print Cloudflare IP ranges
# @alias i
# @option --ip-type <value>    type of IPs ( ipv4 | ipv6 | all ) (default: "all")
# @flag --ip-only              show only addresses (default: false)
# @flag -h --help              show help
ips() {
    :;
}
# }} flarectl ips

# {{ flarectl user
# @cmd User information
# @alias u
# @flag -h --help    show help
user() {
    :;
}

# {{{ flarectl user info
# @cmd User details
# @alias i
user::info() {
    :;
}
# }}} flarectl user info

# {{{ flarectl user update
# @cmd Update user details
# @alias u
user::update() {
    :;
}
# }}} flarectl user update
# }} flarectl user

# {{ flarectl zone
# @cmd Zone information
# @alias z
# @flag -h --help    show help
zone() {
    :;
}

# {{{ flarectl zone list
# @cmd List all zones on an account
# @alias l
zone::list() {
    :;
}
# }}} flarectl zone list

# {{{ flarectl zone create
# @cmd Create a new zone
# @alias c
zone::create() {
    :;
}
# }}} flarectl zone create

# {{{ flarectl zone delete
# @cmd Delete a zone
zone::delete() {
    :;
}
# }}} flarectl zone delete

# {{{ flarectl zone check
# @cmd Initiate a zone activation check
zone::check() {
    :;
}
# }}} flarectl zone check

# {{{ flarectl zone info
# @cmd Information on one zone
# @alias i
zone::info() {
    :;
}
# }}} flarectl zone info

# {{{ flarectl zone lockdown
# @cmd Lockdown a zone based on config
# @alias lo
zone::lockdown() {
    :;
}
# }}} flarectl zone lockdown

# {{{ flarectl zone plan
# @cmd Plan information for one zone
# @alias p
zone::plan() {
    :;
}
# }}} flarectl zone plan

# {{{ flarectl zone settings
# @cmd Settings for one zone
# @alias s
zone::settings() {
    :;
}
# }}} flarectl zone settings

# {{{ flarectl zone purge
# @cmd (Selectively) Purge the cache for a zone
zone::purge() {
    :;
}
# }}} flarectl zone purge

# {{{ flarectl zone dns
# @cmd DNS records for a zone
# @alias d
zone::dns() {
    :;
}
# }}} flarectl zone dns

# {{{ flarectl zone railgun
# @cmd Railguns for a zone
# @alias r
zone::railgun() {
    :;
}
# }}} flarectl zone railgun

# {{{ flarectl zone certs
# @cmd Custom SSL certificates for a zone
# @alias ct
zone::certs() {
    :;
}
# }}} flarectl zone certs

# {{{ flarectl zone keyless
# @cmd Keyless SSL for a zone
# @alias k
zone::keyless() {
    :;
}
# }}} flarectl zone keyless

# {{{ flarectl zone export
# @cmd Export DNS records for a zone
# @alias x
zone::export() {
    :;
}
# }}} flarectl zone export
# }} flarectl zone

# {{ flarectl dns
# @cmd DNS records
# @alias d
# @flag -h --help    show help
dns() {
    :;
}

# {{{ flarectl dns list
# @cmd List DNS records for a zone
# @alias l
dns::list() {
    :;
}
# }}} flarectl dns list

# {{{ flarectl dns create
# @cmd Create a DNS record
# @alias c
dns::create() {
    :;
}
# }}} flarectl dns create

# {{{ flarectl dns update
# @cmd Update a DNS record
# @alias u
dns::update() {
    :;
}
# }}} flarectl dns update

# {{{ flarectl dns create-or-update
# @cmd Create a DNS record, or update if it exists
# @alias o
dns::create-or-update() {
    :;
}
# }}} flarectl dns create-or-update

# {{{ flarectl dns delete
# @cmd Delete a DNS record
# @alias d
dns::delete() {
    :;
}
# }}} flarectl dns delete
# }} flarectl dns

# {{ flarectl user-agents
# @cmd User-Agent blocking
# @alias ua
# @flag -h --help    show help
user-agents() {
    :;
}

# {{{ flarectl user-agents list
# @cmd List User-Agent blocks for a zone
# @alias l
user-agents::list() {
    :;
}
# }}} flarectl user-agents list

# {{{ flarectl user-agents create
# @cmd Create a User-Agent blocking rule
# @alias c
user-agents::create() {
    :;
}
# }}} flarectl user-agents create

# {{{ flarectl user-agents update
# @cmd Update an existing User-Agent block
# @alias u
user-agents::update() {
    :;
}
# }}} flarectl user-agents update

# {{{ flarectl user-agents delete
# @cmd Delete a User-Agent block
# @alias d
user-agents::delete() {
    :;
}
# }}} flarectl user-agents delete
# }} flarectl user-agents

# {{ flarectl pagerules
# @cmd Page Rules
# @alias p
# @flag -h --help    show help
pagerules() {
    :;
}

# {{{ flarectl pagerules list
# @cmd List Page Rules for a zone
# @alias l
pagerules::list() {
    :;
}
# }}} flarectl pagerules list
# }} flarectl pagerules

# {{ flarectl railgun
# @cmd Railgun information
# @alias r
# @flag -h --help    show help
railgun() {
    :;
}
# }} flarectl railgun

# {{ flarectl firewall
# @cmd Firewall
# @alias f
# @flag -h --help    show help
firewall() {
    :;
}

# {{{ flarectl firewall rules
# @cmd Access Rules
# @alias r
firewall::rules() {
    :;
}
# }}} flarectl firewall rules
# }} flarectl firewall

# {{ flarectl origin-ca-root-cert
# @cmd Print Origin CA Root Certificate (in PEM format)
# @alias ocrc
# @option --algorithm <value>    certificate algorithm ( ecc | rsa )
# @flag -h --help                show help
origin-ca-root-cert() {
    :;
}
# }} flarectl origin-ca-root-cert

command eval "$(argc --argc-eval "$0" "$@")"
