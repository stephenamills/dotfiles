_patch_help() { 
    $@ --help | sed 's/^\(\s*-\S\+\),\(-.*\)$/\1, \2/'
}

_patch_table() { 
    _patch_table_edit_options \
        '--activate-profiles;*,[`_choice_profile`]' \
        '--color;[auto|always|never]' \
        '--file(<file:.xml>)' \
        '--global-settings(<file:.xml>)' \
        '--global-toolchains(<file:.xml>)' \
        '--log-file(<file>)' \
        '--projects;*,[`_choice_project`]' \
        '--resume-from;[`_choice_project`]' \
        '--settings(<file:.xml>)' \
        '--toolchains(<file:.xml>)' \
        '-gs(<file:.xml>)' \
        '-gt(<file:.xml>)' \
    | \
    _patch_table_edit_arguments ';;' 'goalAndPhase;*[`_choice_goal_phase`]'
}

_choice_profile() {
    _helper_find_pom_path
    if [[ ! -f "$pom_path" ]]; then
        return
    fi
    cat "$pom_path" | yq -p xml  '.project.profiles[].[].id' 
}

_choice_project() {
    _helper_find_pom_path
    if [[ ! -f "$pom_path" ]]; then
        return
    fi
    mvn --file "$pom_path" -Dexec.executable='echo' -Dexec.args='${project.artifactId}' exec:exec -q
}

_choice_goal_phase() {
    _choice_default_goal_phase
    _helper_find_pom_path
    if [[ ! -f "$pom_path" ]]; then
        return
    fi
    local IFS=$'\n'
    plugin_paths=( $(cat "$pom_path" | yq -p xml '.project.build.plugins.plugin | .[] |  .groupId |= sub("\.", "/") | .groupId + "/" + .artifactId + "/" + .version + "/" + .artifactId + "-" + .version + ".jar"') )
    for plugin_subpath in ${plugin_paths[@]}; do
        plugin_path="$HOME/.m2/repository/$plugin_subpath" 
        if [[ -f "$plugin_path" ]]; then
            unzip -p "$plugin_path" META-INF/maven/plugin.xml | \
            yq -p xml '.plugin.goalPrefix as $prefix | .plugin.mojos[] | .[] | .description |= split("\n") | $prefix + ":" + .goal + "   " + .description[0]'
        fi
    done
}

_choice_default_goal_phase() {
    cat <<-'EOF'
pre-clean	execute processes needed prior to the actual project cleaning
clean	remove all files generated by the previous build
post-clean	execute processes needed to finalize the project cleanin
validate	validate the project is correct and all necessary information is available
initialize	initialize build state, e.g. set properties or create directories
generate-sources	generate any source code for inclusion in compilation
process-sources	process the source code, for example to filter any values
generate-resources	generate resources for inclusion in the package
process-resources	copy and process the resources into the destination directory, ready for packaging
compile	compile the source code of the project
process-classes	post-process the generated files from compilation
generate-test-sources	generate any test source code for inclusion in compilation
process-test-sources	process the test source code, for example to filter any values
generate-test-resources	create resources for testing
process-test-resources	copy and process the resources into the test destination directory
test-compile	compile the test source code into the test destination directory
process-test-classes	post-process the generated files from test compilation
test	run tests using a suitable unit testing framework
prepare-package	perform any operations necessary to prepare a package before the actual packaging
package	take the compiled code and package it in its distributable format, such as a JAR
pre-integration-test	perform actions required before integration tests are executed
integration-test	process and deploy the package into an environment where integration tests can be run
post-integration-test	perform actions required after integration tests have been executed
verify	run any checks to verify the package is valid and meets quality criteria
install	install the package into the local repository
deploy	copies the final package to the remote repository
pre-site	execute processes needed prior to the actual project site generation
site	generate the project's site documentation
post-site	execute processes needed to finalize the site generation
site-deploy	deploy the generated site documentation to the specified web server
EOF
}

_helper_find_pom_path() {
    if [[ -n "$argc_file" ]]; then 
        pom_path="$argc_file"
    else
        pom_path="$(_argc_util_path_search_parent pom.xml)"
    fi
}