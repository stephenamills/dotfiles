#!/usr/bin/env bash
# Automatic generated, DON'T MODIFY IT.

# @flag -v --version    Print the current version of the Northflank cli
# @flag -h --help       Display help for command

# {{ northflank login
# @cmd Connect the CLI to your Northflank account.
# @flag --token-login            Use manual login with API token (default: false)
# @flag --do-not-open-browser    Use browser login but only print URL which can be used to login (default: false)
# @option -n --name              Name for login context
# @option -t --token             Token for this context.
# @option --host                 host url for this context (default: "https://api.northflank.com")
# @flag --override               Override existing contexts (this will remove project and service context) (default: false)
# @flag -h --help                Display help for command
login() {
    :;
}
# }} northflank login

# {{ northflank list
# @cmd List Northflank resources
# @flag -h --help    Display help for command
list() {
    :;
}

# {{{ northflank list log-sinks
# @cmd Gets a list of log sinks added to this account.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::log-sinks() {
    :;
}
# }}} northflank list log-sinks

# {{{ northflank list notifications
# @cmd Lists notification integrations for the authenticated user or team.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::notifications() {
    :;
}
# }}} northflank list notifications

# {{{ northflank list registry-credentials
# @cmd Lists the container registry credentials saved to this account.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::registry-credentials() {
    :;
}
# }}} northflank list registry-credentials

# {{{ northflank list vcs
# @cmd Lists linked version control providers to this account user or team.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::vcs() {
    :;
}
# }}} northflank list vcs

# {{{ northflank list pipelines
# @cmd Lists all pipelines for a project
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --project <PROJECTID>      ID of the project, example: default-project
# @option --projectId <PROJECTID>    ID of the project, example: default-project
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help                    Display help for command
list::pipelines() {
    :;
}
# }}} northflank list pipelines

# {{{ northflank list preview-template-previews
# @cmd Get a list of active preview environments for a template
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help                      Display help for command
list::preview-template-previews() {
    :;
}
# }}} northflank list preview-template-previews

# {{{ northflank list preview-template-runs
# @cmd Get a list of preview template runs
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help                      Display help for command
list::preview-template-runs() {
    :;
}
# }}} northflank list preview-template-runs

# {{{ northflank list release-flow-runs
# @cmd Lists runs of a release flow project project project
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --stage                      Stage of the pipeline, example: development
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help                      Display help for command
list::release-flow-runs() {
    :;
}
# }}} northflank list release-flow-runs

# {{{ northflank list template-runs
# @cmd Get a list of template runs
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --template <TEMPLATEID>      ID of the template, example: example-template
# @option --templateId <TEMPLATEID>    ID of the template, example: example-template
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help                      Display help for command
list::template-runs() {
    :;
}
# }}} northflank list template-runs

# {{{ northflank list cloud
# @cmd Cloud Northflank resources
# @flag -h --help    Display help for command
list::cloud() {
    :;
}

# {{{{ northflank list cloud providers
# @cmd Lists supported cloud providers
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::cloud::providers() {
    :;
}
# }}}} northflank list cloud providers

# {{{{ northflank list cloud clusters
# @cmd Lists clusters for the authenticated user or team.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::cloud::clusters() {
    :;
}
# }}}} northflank list cloud clusters

# {{{{ northflank list cloud docker-registry
# @cmd Lists docker registries for the authenticated user or team.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::cloud::docker-registry() {
    :;
}
# }}}} northflank list cloud docker-registry

# {{{{ northflank list cloud integrations
# @cmd Lists integrations for the authenticated user or team.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::cloud::integrations() {
    :;
}
# }}}} northflank list cloud integrations

# {{{{ northflank list cloud node-types
# @cmd Lists supported cloud provider node types
# @flag --verbose               Verbose output (default: false)
# @flag --quiet                 No console output (default: false)
# @flag --skipValidation        Do not validate input fields on client side (default: false)
# @option --provider            OPTIONAL: If provided, only returns items belonging to this cloud provider., example: gcp
# @option --region              OPTIONAL: If provided, only returns items available in this region., example: europe-west-1
# @option --family              OPTIONAL: If provided, only returns items of this family., example: N
# @option --maxGenerationAge    OPTIONAL: If provided, only returns items with a generation age less than or equal to the number given.
# @option --hasGpu              OPTIONAL: If true, only returns items with GPUs.
# @flag --noDefaults            OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output           OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help               Display help for command
list::cloud::node-types() {
    :;
}
# }}}} northflank list cloud node-types
# }}} northflank list cloud

# {{{ northflank list subdomain
# @cmd Subdomain Northflank resources
# @flag -h --help    Display help for command
list::subdomain() {
    :;
}

# {{{{ northflank list subdomain path
# @cmd List paths for a given subdomain.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @option --subdomain       Name of the subdomain, example: app
# @option --domain          Name of the domain, example: example.com
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml|custom-columns=<column1>,<column2>,...'
# @flag -h --help           Display help for command
list::subdomain::path() {
    :;
}
# }}}} northflank list subdomain path
# }}} northflank list subdomain
# }} northflank list

# {{ northflank get
# @cmd Get information about Northflank resources
# @flag -h --help    Display help for command
get() {
    :;
}

# {{{ northflank get dns-id
# @cmd Returns the partially random string used when generating host names for the authenticated account.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help           Display help for command
get::dns-id() {
    :;
}
# }}} northflank get dns-id

# {{{ northflank get subdomain
# @cmd Gets details about the given subdomain
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @option --subdomain       Name of the subdomain, example: app
# @option --domain          Name of the domain, example: example.com
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help           Display help for command
get::subdomain() {
    :;
}

# {{{{ northflank get subdomain path
# @cmd Get subdomain path details.
# @flag --verbose            Verbose output (default: false)
# @flag --quiet              No console output (default: false)
# @flag --skipValidation     Do not validate input fields on client side (default: false)
# @option --subdomainPath    Name of the path, example: /
# @option --subdomain        Name of the subdomain, example: app
# @option --domain           Name of the domain, example: example.com
# @flag --noDefaults         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help            Display help for command
get::subdomain::path() {
    :;
}
# }}}} northflank get subdomain path
# }}} northflank get subdomain

# {{{ northflank get log-sink
# @cmd Gets details about a given log sink.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --logSink <LOGSINKID>      ID of the log sink, example: example-log-sink
# @option --logSinkId <LOGSINKID>    ID of the log sink, example: example-log-sink
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
get::log-sink() {
    :;
}
# }}} northflank get log-sink

# {{{ northflank get notification
# @cmd Get details about a notification integration.
# @flag --verbose                              Verbose output (default: false)
# @flag --quiet                                No console output (default: false)
# @flag --skipValidation                       Do not validate input fields on client side (default: false)
# @option --notification <NOTIFICATIONID>      ID of the notification integration, example: example-notification-id
# @option --notificationId <NOTIFICATIONID>    ID of the notification integration, example: example-notification-id
# @flag --noDefaults                           OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                          OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                              Display help for command
get::notification() {
    :;
}
# }}} northflank get notification

# {{{ northflank get registry-credentials
# @cmd Views a set of registry credential data.
# @flag --verbose                          Verbose output (default: false)
# @flag --quiet                            No console output (default: false)
# @flag --skipValidation                   Do not validate input fields on client side (default: false)
# @option --credential <CREDENTIALID>      ID of the registry credential, example: example-credentials
# @option --credentialId <CREDENTIALID>    ID of the registry credential, example: example-credentials
# @flag --noDefaults                       OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                      OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                          Display help for command
get::registry-credentials() {
    :;
}
# }}} northflank get registry-credentials

# {{{ northflank get pipeline
# @cmd Get details about a pipeline
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
get::pipeline() {
    :;
}
# }}} northflank get pipeline

# {{{ northflank get preview-template
# @cmd Get information about the given preview template.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
get::preview-template() {
    :;
}
# }}} northflank get preview-template

# {{{ northflank get preview-template-run
# @cmd Get information about the given preview template run.
# @flag --verbose                            Verbose output (default: false)
# @flag --quiet                              No console output (default: false)
# @flag --skipValidation                     Do not validate input fields on client side (default: false)
# @option --templateRun <TEMPLATERUNID>      ID of the template run, example: 16cf800b-ab28-421a-8ff9-a935b5ee89ad
# @option --templateRunId <TEMPLATERUNID>    ID of the template run, example: 16cf800b-ab28-421a-8ff9-a935b5ee89ad
# @option --pipeline <PIPELINEID>            ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>          ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>              ID of the project, example: default-project
# @option --projectId <PROJECTID>            ID of the project, example: default-project
# @flag --noDefaults                         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                            Display help for command
get::preview-template-run() {
    :;
}
# }}} northflank get preview-template-run

# {{{ northflank get release-flow
# @cmd Gets details about a release flow
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --stage                      Stage of the pipeline, example: development
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
get::release-flow() {
    :;
}
# }}} northflank get release-flow

# {{{ northflank get release-flow-run
# @cmd Get information about the given release flow run
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --run <RUNID>                ID of the release flow run, example: development
# @option --runId <RUNID>              ID of the release flow run, example: development
# @option --stage                      Stage of the pipeline, example: development
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
get::release-flow-run() {
    :;
}
# }}} northflank get release-flow-run

# {{{ northflank get secret-link
# @cmd Get details about a given addon link.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --addon <ADDONID>          ID of the addon, example: example-addon
# @option --addonId <ADDONID>        ID of the addon, example: example-addon
# @option --secret <SECRETID>        ID of the secret, example: example-secret
# @option --secretId <SECRETID>      ID of the secret, example: example-secret
# @option --project <PROJECTID>      ID of the project, example: default-project
# @option --projectId <PROJECTID>    ID of the project, example: default-project
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
get::secret-link() {
    :;
}
# }}} northflank get secret-link

# {{{ northflank get secret-details
# @cmd View a secret with details about its linked addons
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --secret <SECRETID>        ID of the secret, example: example-secret
# @option --secretId <SECRETID>      ID of the secret, example: example-secret
# @option --project <PROJECTID>      ID of the project, example: default-project
# @option --projectId <PROJECTID>    ID of the project, example: default-project
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
get::secret-details() {
    :;
}
# }}} northflank get secret-details

# {{{ northflank get template-run
# @cmd Get information about the given template run.
# @flag --verbose                            Verbose output (default: false)
# @flag --quiet                              No console output (default: false)
# @flag --skipValidation                     Do not validate input fields on client side (default: false)
# @option --templateRun <TEMPLATERUNID>      ID of the template run, example: 16cf800b-ab28-421a-8ff9-a935b5ee89ad
# @option --templateRunId <TEMPLATERUNID>    ID of the template run, example: 16cf800b-ab28-421a-8ff9-a935b5ee89ad
# @option --template <TEMPLATEID>            ID of the template, example: example-template
# @option --templateId <TEMPLATEID>          ID of the template, example: example-template
# @flag --noDefaults                         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                            Display help for command
get::template-run() {
    :;
}
# }}} northflank get template-run

# {{{ northflank get cloud
# @cmd Get information about Northflank clouds
# @flag -h --help    Display help for command
get::cloud() {
    :;
}

# {{{{ northflank get cloud cluster
# @cmd Get information about the given cluster
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --cluster <CLUSTERID>      ID of the cluster, example: gcp-cluster-1
# @option --clusterId <CLUSTERID>    ID of the cluster, example: gcp-cluster-1
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
get::cloud::cluster() {
    :;
}
# }}}} northflank get cloud cluster

# {{{{ northflank get cloud docker-registry
# @cmd Get information about the given docker registry
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --registry <REGISTRYID>      ID of the docker registry, example: docker-registry-1
# @option --registryId <REGISTRYID>    ID of the docker registry, example: docker-registry-1
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
get::cloud::docker-registry() {
    :;
}
# }}}} northflank get cloud docker-registry

# {{{{ northflank get cloud integration
# @cmd Get information about the given integration
# @flag --verbose                            Verbose output (default: false)
# @flag --quiet                              No console output (default: false)
# @flag --skipValidation                     Do not validate input fields on client side (default: false)
# @option --integration <INTEGRATIONID>      ID of the provider integration, example: gcp-integration-1
# @option --integrationId <INTEGRATIONID>    ID of the provider integration, example: gcp-integration-1
# @flag --noDefaults                         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                            Display help for command
get::cloud::integration() {
    :;
}
# }}}} northflank get cloud integration
# }}} northflank get cloud
# }} northflank get

# {{ northflank create
# @cmd Create Northflank resources
# @flag -h --help    Display help for command
create() {
    :;
}

# {{{ northflank create log-sink
# @cmd Creates a new log sink.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
create::log-sink() {
    :;
}
# }}} northflank create log-sink

# {{{ northflank create notification
# @cmd Create a new notification integration.
# @flag --verbose                              Verbose output (default: false)
# @flag --quiet                                No console output (default: false)
# @flag --skipValidation                       Do not validate input fields on client side (default: false)
# @option -f --file <file-path>                File to load resource json from
# @option -i --input <resource-def>            JSON-formatted resource definition, takes precedence over "--file"
# @option --notification <NOTIFICATIONID>      ID of the notification integration, example: example-notification-id
# @option --notificationId <NOTIFICATIONID>    ID of the notification integration, example: example-notification-id
# @flag --noDefaults                           OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                          OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                              Display help for command
create::notification() {
    :;
}
# }}} northflank create notification

# {{{ northflank create cloud
# @cmd Cloud Northflank resources
# @flag -h --help    Display help for command
create::cloud() {
    :;
}

# {{{{ northflank create cloud cluster
# @cmd Creates a new cluster.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
create::cloud::cluster() {
    :;
}
# }}}} northflank create cloud cluster

# {{{{ northflank create cloud docker-registry
# @cmd Creates a new docker registry.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
create::cloud::docker-registry() {
    :;
}
# }}}} northflank create cloud docker-registry

# {{{{ northflank create cloud integration
# @cmd Creates a new integration.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
create::cloud::integration() {
    :;
}
# }}}} northflank create cloud integration
# }}} northflank create cloud

# {{{ northflank create custom-vcs
# @cmd CustomVcs Northflank resources
# @flag -h --help    Display help for command
create::custom-vcs() {
    :;
}

# {{{{ northflank create custom-vcs token
# @cmd Generate a token for a specific VCS link.
# @flag --verbose                        Verbose output (default: false)
# @flag --quiet                          No console output (default: false)
# @flag --skipValidation                 Do not validate input fields on client side (default: false)
# @option --vcsLink <VCSLINKID>          ID of the version control link, example: 63ebb6ce2ccc6c7affdbf253
# @option --vcsLinkId <VCSLINKID>        ID of the version control link, example: 63ebb6ce2ccc6c7affdbf253
# @option --customVCS <CUSTOMVCSID>      ID of the custom VCS, example: cdb3d41f-0dd8-49ad-92d5-7544c98c490b
# @option --customVCSId <CUSTOMVCSID>    ID of the custom VCS, example: cdb3d41f-0dd8-49ad-92d5-7544c98c490b
# @option --force_refresh                OPTIONAL: undefined
# @flag --noDefaults                     OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                    OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                        Display help for command
create::custom-vcs::token() {
    :;
}
# }}}} northflank create custom-vcs token
# }}} northflank create custom-vcs
# }} northflank create

# {{ northflank delete
# @cmd Delete Northflank resources
# @flag -h --help    Display help for command
delete() {
    :;
}

# {{{ northflank delete subdomain
# @cmd Removes a subdomain from a domain.
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @option --subdomain       Name of the subdomain, example: app
# @option --domain          Name of the domain, example: example.com
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force             OPTIONAL: Don't ask for confirmation.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help           Display help for command
delete::subdomain() {
    :;
}

# {{{{ northflank delete subdomain path
# @cmd Delete a path.
# @flag --verbose            Verbose output (default: false)
# @flag --quiet              No console output (default: false)
# @flag --skipValidation     Do not validate input fields on client side (default: false)
# @option --subdomainPath    Name of the path, example: /
# @option --subdomain        Name of the subdomain, example: app
# @option --domain           Name of the domain, example: example.com
# @flag --noDefaults         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force              OPTIONAL: Don't ask for confirmation.
# @option -o --output        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help            Display help for command
delete::subdomain::path() {
    :;
}
# }}}} northflank delete subdomain path
# }}} northflank delete subdomain

# {{{ northflank delete log-sink
# @cmd Deletes a log sink.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --logSink <LOGSINKID>      ID of the log sink, example: example-log-sink
# @option --logSinkId <LOGSINKID>    ID of the log sink, example: example-log-sink
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                      OPTIONAL: Don't ask for confirmation.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
delete::log-sink() {
    :;
}
# }}} northflank delete log-sink

# {{{ northflank delete notification
# @cmd Deletes a notification integration
# @flag --verbose                              Verbose output (default: false)
# @flag --quiet                                No console output (default: false)
# @flag --skipValidation                       Do not validate input fields on client side (default: false)
# @option --notification <NOTIFICATIONID>      ID of the notification integration, example: example-notification-id
# @option --notificationId <NOTIFICATIONID>    ID of the notification integration, example: example-notification-id
# @flag --noDefaults                           OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                                OPTIONAL: Don't ask for confirmation.
# @option -o --output                          OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                              Display help for command
delete::notification() {
    :;
}
# }}} northflank delete notification

# {{{ northflank delete registry-credentials
# @cmd Deletes a set of registry credential data.
# @flag --verbose                          Verbose output (default: false)
# @flag --quiet                            No console output (default: false)
# @flag --skipValidation                   Do not validate input fields on client side (default: false)
# @option --credential <CREDENTIALID>      ID of the registry credential, example: example-credentials
# @option --credentialId <CREDENTIALID>    ID of the registry credential, example: example-credentials
# @flag --noDefaults                       OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                            OPTIONAL: Don't ask for confirmation.
# @option -o --output                      OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                          Display help for command
delete::registry-credentials() {
    :;
}
# }}} northflank delete registry-credentials

# {{{ northflank delete backup
# @cmd Deletes a given backup
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --backup <BACKUPID>        ID of the backup, example: example-backup
# @option --backupId <BACKUPID>      ID of the backup, example: example-backup
# @option --addon <ADDONID>          ID of the addon, example: example-addon
# @option --addonId <ADDONID>        ID of the addon, example: example-addon
# @option --project <PROJECTID>      ID of the project, example: default-project
# @option --projectId <PROJECTID>    ID of the project, example: default-project
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                      OPTIONAL: Don't ask for confirmation.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
delete::backup() {
    :;
}
# }}} northflank delete backup

# {{{ northflank delete preview-template-preview
# @cmd Delete a preview environment generated by a preview template.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --preview <PREVIEWID>        ID of the preview environment, example: different-ray
# @option --previewId <PREVIEWID>      ID of the preview environment, example: different-ray
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                        OPTIONAL: Don't ask for confirmation.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
delete::preview-template-preview() {
    :;
}
# }}} northflank delete preview-template-preview

# {{{ northflank delete secret-link
# @cmd Unlinks an addon from the secret group.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --addon <ADDONID>          ID of the addon, example: example-addon
# @option --addonId <ADDONID>        ID of the addon, example: example-addon
# @option --secret <SECRETID>        ID of the secret, example: example-secret
# @option --secretId <SECRETID>      ID of the secret, example: example-secret
# @option --project <PROJECTID>      ID of the project, example: default-project
# @option --projectId <PROJECTID>    ID of the project, example: default-project
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                      OPTIONAL: Don't ask for confirmation.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
delete::secret-link() {
    :;
}
# }}} northflank delete secret-link

# {{{ northflank delete cloud
# @cmd Cloud Northflank resources
# @flag -h --help    Display help for command
delete::cloud() {
    :;
}

# {{{{ northflank delete cloud cluster
# @cmd Delete the given cluster.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --cluster <CLUSTERID>      ID of the cluster, example: gcp-cluster-1
# @option --clusterId <CLUSTERID>    ID of the cluster, example: gcp-cluster-1
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                      OPTIONAL: Don't ask for confirmation.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
delete::cloud::cluster() {
    :;
}
# }}}} northflank delete cloud cluster

# {{{{ northflank delete cloud docker-registry
# @cmd Delete the given docker registry.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --registry <REGISTRYID>      ID of the docker registry, example: docker-registry-1
# @option --registryId <REGISTRYID>    ID of the docker registry, example: docker-registry-1
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                        OPTIONAL: Don't ask for confirmation.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
delete::cloud::docker-registry() {
    :;
}
# }}}} northflank delete cloud docker-registry

# {{{{ northflank delete cloud integration
# @cmd Delete the given integration.
# @flag --verbose                            Verbose output (default: false)
# @flag --quiet                              No console output (default: false)
# @flag --skipValidation                     Do not validate input fields on client side (default: false)
# @option --integration <INTEGRATIONID>      ID of the provider integration, example: gcp-integration-1
# @option --integrationId <INTEGRATIONID>    ID of the provider integration, example: gcp-integration-1
# @flag --noDefaults                         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @flag --force                              OPTIONAL: Don't ask for confirmation.
# @option -o --output                        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                            Display help for command
delete::cloud::integration() {
    :;
}
# }}}} northflank delete cloud integration
# }}} northflank delete cloud
# }} northflank delete

# {{ northflank import
# @cmd Import Northflank resources
# @flag -h --help    Display help for command
import() {
    :;
}

# {{{ northflank import domain-certificate
# @cmd Import a certificate for the domain
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --domain                     Name of the domain, example: example.com
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
import::domain-certificate() {
    :;
}
# }}} northflank import domain-certificate
# }} northflank import

# {{ northflank unassign
# @cmd Unassign Northflank resources
# @flag -h --help    Display help for command
unassign() {
    :;
}

# {{{ northflank unassign subdomain
# @cmd Removes a subdomain from its assigned service
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @option --subdomain       Name of the subdomain, example: app
# @option --domain          Name of the domain, example: example.com
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help           Display help for command
unassign::subdomain() {
    :;
}

# {{{{ northflank unassign subdomain path
# @cmd Unassign a subdomain path to a port.
# @flag --verbose            Verbose output (default: false)
# @flag --quiet              No console output (default: false)
# @flag --skipValidation     Do not validate input fields on client side (default: false)
# @option --subdomainPath    Name of the path, example: /
# @option --subdomain        Name of the subdomain, example: app
# @option --domain           Name of the domain, example: example.com
# @flag --noDefaults         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help            Display help for command
unassign::subdomain::path() {
    :;
}
# }}}} northflank unassign subdomain path
# }}} northflank unassign subdomain
# }} northflank unassign

# {{ northflank verify
# @cmd Verify Northflank resources
# @flag -h --help    Display help for command
verify() {
    :;
}

# {{{ northflank verify subdomain
# @cmd Gets details about the given subdomain
# @flag --verbose           Verbose output (default: false)
# @flag --quiet             No console output (default: false)
# @flag --skipValidation    Do not validate input fields on client side (default: false)
# @option --subdomain       Name of the subdomain, example: app
# @option --domain          Name of the domain, example: example.com
# @flag --noDefaults        OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output       OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help           Display help for command
verify::subdomain() {
    :;
}
# }}} northflank verify subdomain
# }} northflank verify

# {{ northflank pause
# @cmd Pause Northflank resources
# @flag -h --help    Display help for command
pause() {
    :;
}

# {{{ northflank pause log-sink
# @cmd Pauses a given log sink.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --logSink <LOGSINKID>      ID of the log sink, example: example-log-sink
# @option --logSinkId <LOGSINKID>    ID of the log sink, example: example-log-sink
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
pause::log-sink() {
    :;
}
# }}} northflank pause log-sink
# }} northflank pause

# {{ northflank resume
# @cmd Resume Northflank resources
# @flag -h --help    Display help for command
resume() {
    :;
}

# {{{ northflank resume log-sink
# @cmd Resumes a paused log sink.
# @flag --verbose                    Verbose output (default: false)
# @flag --quiet                      No console output (default: false)
# @flag --skipValidation             Do not validate input fields on client side (default: false)
# @option --logSink <LOGSINKID>      ID of the log sink, example: example-log-sink
# @option --logSinkId <LOGSINKID>    ID of the log sink, example: example-log-sink
# @flag --noDefaults                 OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                    Display help for command
resume::log-sink() {
    :;
}
# }}} northflank resume log-sink
# }} northflank resume

# {{ northflank update
# @cmd Update Northflank resource properties
# @flag -h --help    Display help for command
update() {
    :;
}

# {{{ northflank update log-sink
# @cmd Updates the settings for a log sink.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --logSink <LOGSINKID>        ID of the log sink, example: example-log-sink
# @option --logSinkId <LOGSINKID>      ID of the log sink, example: example-log-sink
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
update::log-sink() {
    :;
}
# }}} northflank update log-sink

# {{{ northflank update notification
# @cmd Updates a notification integration
# @flag --verbose                              Verbose output (default: false)
# @flag --quiet                                No console output (default: false)
# @flag --skipValidation                       Do not validate input fields on client side (default: false)
# @option -f --file <file-path>                File to load resource json from
# @option -i --input <resource-def>            JSON-formatted resource definition, takes precedence over "--file"
# @option --notification <NOTIFICATIONID>      ID of the notification integration, example: example-notification-id
# @option --notificationId <NOTIFICATIONID>    ID of the notification integration, example: example-notification-id
# @flag --noDefaults                           OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                          OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                              Display help for command
update::notification() {
    :;
}
# }}} northflank update notification

# {{{ northflank update registry-credentials
# @cmd Updates a set of registry credential data.
# @flag --verbose                          Verbose output (default: false)
# @flag --quiet                            No console output (default: false)
# @flag --skipValidation                   Do not validate input fields on client side (default: false)
# @option -f --file <file-path>            File to load resource json from
# @option -i --input <resource-def>        JSON-formatted resource definition, takes precedence over "--file"
# @option --credential <CREDENTIALID>      ID of the registry credential, example: example-credentials
# @option --credentialId <CREDENTIALID>    ID of the registry credential, example: example-credentials
# @flag --noDefaults                       OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                      OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                          Display help for command
update::registry-credentials() {
    :;
}
# }}} northflank update registry-credentials

# {{{ northflank update preview-template
# @cmd Update a given preview template.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
update::preview-template() {
    :;
}
# }}} northflank update preview-template

# {{{ northflank update release-flow
# @cmd Updates a release flow
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --stage                      Stage of the pipeline, example: development
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
update::release-flow() {
    :;
}
# }}} northflank update release-flow

# {{{ northflank update secret-link
# @cmd Link an addon to the secret group or edit the settings of the linked addon.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --addon <ADDONID>            ID of the addon, example: example-addon
# @option --addonId <ADDONID>          ID of the addon, example: example-addon
# @option --secret <SECRETID>          ID of the secret, example: example-secret
# @option --secretId <SECRETID>        ID of the secret, example: example-secret
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
update::secret-link() {
    :;
}
# }}} northflank update secret-link

# {{{ northflank update cloud
# @cmd Update Northflank cloud properties
# @flag -h --help    Display help for command
update::cloud() {
    :;
}

# {{{{ northflank update cloud cluster
# @cmd Update an existing cluster.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --cluster <CLUSTERID>        ID of the cluster, example: gcp-cluster-1
# @option --clusterId <CLUSTERID>      ID of the cluster, example: gcp-cluster-1
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
update::cloud::cluster() {
    :;
}
# }}}} northflank update cloud cluster

# {{{{ northflank update cloud integration
# @cmd Update information about the given integration
# @flag --verbose                            Verbose output (default: false)
# @flag --quiet                              No console output (default: false)
# @flag --skipValidation                     Do not validate input fields on client side (default: false)
# @option -f --file <file-path>              File to load resource json from
# @option -i --input <resource-def>          JSON-formatted resource definition, takes precedence over "--file"
# @option --integration <INTEGRATIONID>      ID of the provider integration, example: gcp-integration-1
# @option --integrationId <INTEGRATIONID>    ID of the provider integration, example: gcp-integration-1
# @flag --noDefaults                         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                            Display help for command
update::cloud::integration() {
    :;
}
# }}}} northflank update cloud integration
# }}} northflank update cloud

# {{{ northflank update subdomain
# @cmd Update Northflank subdomain properties
# @flag -h --help    Display help for command
update::subdomain() {
    :;
}

# {{{{ northflank update subdomain path
# @cmd Update a subdomain path.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --subdomainPath              Name of the path, example: /
# @option --subdomain                  Name of the subdomain, example: app
# @option --domain                     Name of the domain, example: example.com
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
update::subdomain::path() {
    :;
}
# }}}} northflank update subdomain path
# }}} northflank update subdomain
# }} northflank update

# {{ northflank add
# @cmd Add Northflank resources
# @flag -h --help    Display help for command
add() {
    :;
}

# {{{ northflank add registry-credentials
# @cmd Adds a new set of container registry credentials to this account.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
add::registry-credentials() {
    :;
}
# }}} northflank add registry-credentials

# {{{ northflank add subdomain
# @cmd Subdomain Northflank resources
# @flag -h --help    Display help for command
add::subdomain() {
    :;
}

# {{{{ northflank add subdomain path
# @cmd Adds a new path to the subdomain.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --subdomain                  Name of the subdomain, example: app
# @option --domain                     Name of the domain, example: example.com
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
add::subdomain::path() {
    :;
}
# }}}} northflank add subdomain path
# }}} northflank add subdomain
# }} northflank add

# {{ northflank put
# @cmd Put Northflank resources
# @flag -h --help    Display help for command
put() {
    :;
}
# }} northflank put

# {{ northflank patch
# @cmd Patch Northflank resources
# @flag -h --help    Display help for command
# @arg command
patch() {
    :;
}
# }} northflank patch

# {{ northflank backup
# @cmd Backup Northflank resources
# @flag -h --help    Display help for command
# @arg command
backup() {
    :;
}
# }} northflank backup

# {{ northflank reset
# @cmd Reset Northflank resources
# @flag -h --help    Display help for command
# @arg command
reset() {
    :;
}
# }} northflank reset

# {{ northflank restart
# @cmd Restart Northflank resources
# @flag -h --help    Display help for command
# @arg command
restart() {
    :;
}
# }} northflank restart

# {{ northflank scale
# @cmd Scale Northflank resources
# @flag -h --help    Display help for command
scale() {
    :;
}
# }} northflank scale

# {{ northflank suspend
# @cmd Suspend Northflank resources
# @flag -h --help    Display help for command
# @arg command
suspend() {
    :;
}
# }} northflank suspend

# {{ northflank run
# @cmd Run Northflank resources
# @flag -h --help    Display help for command
run() {
    :;
}

# {{{ northflank run release-flow
# @cmd Runs a given release flow with given arguments.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --stage                      Stage of the pipeline, example: development
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
run::release-flow() {
    :;
}
# }}} northflank run release-flow
# }} northflank run

# {{ northflank abort
# @cmd Abort Northflank resources
# @flag -h --help    Display help for command
abort() {
    :;
}

# {{{ northflank abort release-flow-run
# @cmd Abort the given release flow run
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option --run <RUNID>                ID of the release flow run, example: development
# @option --runId <RUNID>              ID of the release flow run, example: development
# @option --stage                      Stage of the pipeline, example: development
# @option --pipeline <PIPELINEID>      ID of the pipeline, example: example-pipeline
# @option --pipelineId <PIPELINEID>    ID of the pipeline, example: example-pipeline
# @option --project <PROJECTID>        ID of the project, example: default-project
# @option --projectId <PROJECTID>      ID of the project, example: default-project
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
abort::release-flow-run() {
    :;
}
# }}} northflank abort release-flow-run

# {{{ northflank abort template-run
# @cmd Abort the given template run.
# @flag --verbose                            Verbose output (default: false)
# @flag --quiet                              No console output (default: false)
# @flag --skipValidation                     Do not validate input fields on client side (default: false)
# @option --templateRun <TEMPLATERUNID>      ID of the template run, example: 16cf800b-ab28-421a-8ff9-a935b5ee89ad
# @option --templateRunId <TEMPLATERUNID>    ID of the template run, example: 16cf800b-ab28-421a-8ff9-a935b5ee89ad
# @option --template <TEMPLATEID>            ID of the template, example: example-template
# @option --templateId <TEMPLATEID>          ID of the template, example: example-template
# @flag --noDefaults                         OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                        OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                            Display help for command
abort::template-run() {
    :;
}
# }}} northflank abort template-run
# }} northflank abort

# {{ northflank attach
# @cmd Attach Northflank resources
# @flag -h --help    Display help for command
# @arg command
attach() {
    :;
}
# }} northflank attach

# {{ northflank detach
# @cmd Detach Northflank resources
# @flag -h --help    Display help for command
# @arg command
detach() {
    :;
}
# }} northflank detach

# {{ northflank assign
# @cmd Assign Northflank resources
# @flag -h --help    Display help for command
assign() {
    :;
}

# {{{ northflank assign subdomain
# @cmd Subdomain Northflank resources
# @flag -h --help    Display help for command
assign::subdomain() {
    :;
}

# {{{{ northflank assign subdomain path
# @cmd Assign a subdomain path to a port.
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --subdomainPath              Name of the path, example: /
# @option --subdomain                  Name of the subdomain, example: app
# @option --domain                     Name of the domain, example: example.com
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
assign::subdomain::path() {
    :;
}
# }}}} northflank assign subdomain path
# }}} northflank assign subdomain
# }} northflank assign

# {{ northflank disable
# @cmd Disable Northflank resources
# @flag -h --help    Display help for command
disable() {
    :;
}

# {{{ northflank disable subdomain
# @cmd Subdomain Northflank resources
# @flag -h --help    Display help for command
disable::subdomain() {
    :;
}

# {{{{ northflank disable subdomain cdn
# @cmd Removes the CDN integration from the given subdomain
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --subdomain                  Name of the subdomain, example: app
# @option --domain                     Name of the domain, example: example.com
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
disable::subdomain::cdn() {
    :;
}
# }}}} northflank disable subdomain cdn
# }}} northflank disable subdomain
# }} northflank disable

# {{ northflank enable
# @cmd Enable Northflank resources
# @flag -h --help    Display help for command
enable() {
    :;
}

# {{{ northflank enable subdomain
# @cmd Subdomain Northflank resources
# @flag -h --help    Display help for command
enable::subdomain() {
    :;
}

# {{{{ northflank enable subdomain cdn
# @cmd Enables a CDN integration on the given subdomain
# @flag --verbose                      Verbose output (default: false)
# @flag --quiet                        No console output (default: false)
# @flag --skipValidation               Do not validate input fields on client side (default: false)
# @option -f --file <file-path>        File to load resource json from
# @option -i --input <resource-def>    JSON-formatted resource definition, takes precedence over "--file"
# @option --subdomain                  Name of the subdomain, example: app
# @option --domain                     Name of the domain, example: example.com
# @flag --noDefaults                   OPTIONAL: Don't use context default values, explicitly use options or ask.
# @option -o --output                  OPTIONAL: Output formatting, options: '--output json|yaml'
# @flag -h --help                      Display help for command
enable::subdomain::cdn() {
    :;
}
# }}}} northflank enable subdomain cdn
# }}} northflank enable subdomain
# }} northflank enable

# {{ northflank restore
# @cmd Restore Northflank resources
# @flag -h --help    Display help for command
# @arg command
restore() {
    :;
}
# }} northflank restore

# {{ northflank retain
# @cmd Retain Northflank resources
# @flag -h --help    Display help for command
# @arg command
retain() {
    :;
}
# }} northflank retain

# {{ northflank start
# @cmd Start Northflank resources
# @flag -h --help    Display help for command
# @arg command
start() {
    :;
}
# }} northflank start

command eval "$(argc --argc-eval "$0" "$@")"
