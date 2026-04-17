# The `RELEASE.yaml` File

This file is both notational for the Development and Release teams and
used by automation to perform code freeze branching for on-prem
releases.  See the
[latest spec](https://datarobot.atlassian.net/wiki/spaces/Ignite/pages/5618761738/Distributed+Release+Metadata+-+RELEASE.yaml)

## General

The format of this file is based on YAML representation. Fields should all be text unless
otherwise directed.

All fields are required unless otherwise noted.

There is now only one major version 2.0. It is shown in use by being a
file called RELEASE.yaml that has replaced BRANCHING.yaml.

### The Release Process

The presence of this file presumes your repository is shipped as part
of our product. As a result the repo is subject to our Information
Security Policy and requirements for ISO 27001 and SOC 2
compliance. This includes branch protections, correct permissions for
branch-admins, etc as stated in the
[Checklist for Production Software](https://datarobot.atlassian.net/wiki/spaces/Architecture/pages/5632426163).

Additionally, it means the repo will be branched as part of our
Enterprise Release processes. This means it is subject to branching
and tagging required for that process. Automations will discover
RELEASE.yaml files and create `release/X.X` branches on each branch
cut date. It will also create tags of the pattern
`release/X.X-branchpoint`.  It will also create any additional tag
patterns you specify in your RELEASE.yaml via the array of tags.

Be sure to account for these patterns for common SCM release build
systems.

After branch cut the file is also used to discover and identify
[Acceptance Tests](https://datarobot.atlassian.net/wiki/spaces/Ignite/pages/5618925578/Acceptance+Testing+for+Multi-+Cloud+Repo)
that will run be automatically discovered and executed in our
Regression Pipelines. At a future date, it may also execute
Performance Tests.

The third process we use RELEASE.yaml for is to continuously identify
vulnerabilities and third-party libraries in our Enterprise product
(Single Tenant SaaS, VPC, and On-Prem). We will pull in the specified
Trivy Ignore Policy for your repo to reduce false positives, allow
managed exceptions to discovered CVEs, and allow reviewed high risk
third party software such as GPL licensed packages in our base OS
images.

### Dry Runs

To test our automation and continue developing and ensuring all repos are ready
for the Enterprise Release branch cut, we will periodically do dry runs. The dry runs will
create branches and tags with a `-DRY-RUN` suffix added to the version, i.e., `10.0-DRY-RUN`.


### Status

At this time (2024-04-03) version 2.0 features are fully
supported. Regression pipelines now fully incorporate Acceptance Tests
and Trivy ignore files for enterprise release.

## Top-Level Keys


### `description`

> Version: 1.0

This is a free-form text field that describes the core purpose of the repository. It doesn't
have to be long, as the details of the repo should be in a README file. Instead, it should get the point
across in one or two sentences, and should make it clear why it's important to branch it.

### `production`

> Version: 2.0

Boolean, allowed values are `true`|`false`.

If set to `false`, the repository will be excluded from any discovery process, i.e. for the branch cut,
acceptance test scheduling, etc.

If not set at all, it defaults to `true`.

### `meta`

> Version: 1.0

> *Optional*

Meta document information. A dictionary of values with the following keys:

* `version` - Provide a string that indicates the version of this format to use in semantic versioning form.
  This field is implicitly the latest version based on the file name. Example: `1.0.0` or `2.0.1`

### `artifact_build_job`

> Version: 1.0 _ONLY_

> *Optional*

The path to an HQ jenkins job that will be run to prepare artifacts on the new branch,
after the branch is cut.

_Note_ The usage of this field was inconsistent and could appear spaces instead of underscores.

### `artifact_prepare_job`

> Version: 1.0 _ONLY_

> *Optional*

Yet another one-off 1.0 way of specifying artifact build jobs. This is just a string.

### `artifact_prepare_parameters`

> Version: 1.0 _ONLY_

> *Optional*

Goes with [artifact_prepare_job](#artifact_prepare_job) A dictionary of name/value pairs
to hand to the job.

### `post_branch_cut_pipelines`

> Version 2.0+

> Optional

A list of dictionaries that define the jobs that are run after the branch is cut. Each job is defined
in terms of these parameters. All values in these parameters are variable-expanded
(see [Variables](#Variables)).

* `host` - The service host to use to kick off the job
* `service` - The type of service to use to run the job (e.g. `jenkins`, `harness`, or `POST`)
* `endpoint` - The job endpoint
    * `<job-name>` for `jenkins`
    * `<organization-name>/projects/<project-name>/pipelines/<pipeline-name>` for `harness`
    * Any arbitary path for `POST`
* `variables` - A dictionary of additional variables to pass to the endpoint

### `artifact_build_parameters`

> Version 1.0 ONLY

> *Optional*

A dictionary of parameters to pass to the [artifact_build_job](#artifact_build_job).


### `additional_jobs_to_be_updated` (with or without underscores)

> Version 1.0 ONLY

> *Optional*

A list of HQ Jenkins job paths equivalent to [artifact_build_job](#artifact_build_job).
f you need to run secondary jobs, this is where they should be listed.

### `master-pins`

> REMOVED, Version 1.0 ONLY

> *Optional*

Ignored. Only used notationally for information on how to post-branch-cut update
the master branch.

### `pins`

Local files that should be updated during branch cut (before the branch is locked).

The value is a list of dictionaries with the following entries:

* `file` - The file to update, relative to the repository root. (_required_)
* `value` - The value to overwrite the `file` with (_optional_; must be set if `command` unset)
* `command` - The command to run against `file` (e.g. with `sed`) to replace the value (_optional_; must be set if `value` unset)

### `tags`

> Version 1.0

> *Optional*

When the repository is branched, before the branch is made public, tags can be added in git. By default
a tag will be added to the version on the base branch that was branched *from*, but no tag is added
to the new branch.

The value is a list of dictionaries with the following keys:

* `name` - A descriptive name (in version 2.0+ used as the tag "message") (_required_)
* `value` - (Version: 2.0) the tag's label (the name seen by git users) (_required_ in 2.0+)
* `git` - (Version: 1.0 ONLY) the git command to run, without "git" (e.g. `tag {}.0.1`) (_required_ in 1.0)

### `future_proof_automation`

> Version 1.0 ONLY

> *Optional*

A list of strings, notational only, no tooling uses this.

### `trivy-policy`

> Version 2.0

> *Optional*

The path to the
[Trivy Rego Policy](https://aquasecurity.github.io/trivy/v0.41/docs/scanner/misconfiguration/custom/)
for handling OSS Compliance and CVE exceptions.

### `acceptance-tests`

> Version 2.0

> *Optional*

A dictionary that defines the acceptance test pipeline to run against an
installed platform to validate the software is working correctly per
[PBMP-5670](https://docs.google.com/document/d/1uU_POHMTVFrcVVjO8y30ean0Gk93TUuU7ya-vRkwGkw/edit).
Each pipeline is defined in terms of these parameters. All values in
these parameters are variable-expanded (see [Variables](#Variables)).

* `host` - The service host to use to kick off the job
* `service` - The type of service to use to run the job (i.e. `jenkins`, `harness`, or `POST`)
* `endpoint` - The job endpoint
    * `<job-name>` for `jenkins`
    * `<organization-name>/projects/<project-name>/pipelines/<pipeline-name>` for `harness`
    * Any arbitary path for `POST`
* `variables` - A dictionary of additional variables to pass to the endpoint. See below the full list
of available variables

#### Harness examples:
Basic with minimal amount of variables
```yaml
acceptance-tests:
  service: harness
  endpoint: CIIT/projects/awesome_project/pipelines/Independent_Acceptance_Tests
  variables:
    VERSION_REF: "{version}"
    DATAROBOT_URL: "{end_user_uri}"
    DATAROBOT_API_TOKEN: "{app_admin_api_key}"
    DATAROBOT_USERNAME: "{app_admin_username}"
```
Advanced with raw input-set from Harness.
```yaml
acceptance-tests:
  service: harness
  endpoint: CIIT/projects/awesome_project/pipelines/Independent_Acceptance_Tests
  input_set:
    pipeline:
      identifier: Independent_Acceptance_Tests
      template:
        templateInputs:
          properties:
            ci:
              codebase:
                build:
                  spec:
                    type: branch
                    spec:
                      branch: "{version}"
          stages:
            - stage:
              identifier: Get_Deployment_Info
              type: Custom
              variables:
                - name: SERVICE_NAMESPACE
                  type: String
                  value: "{namespace}"
              spec:
                environment:
                  environmentRef: "{cluster_name}"
                  infrastructureDefinitions:
                    - identifier: "{environ_name}"
                      inputs:
                        identifier: "{environ_name}"
                        type: KubernetesDirect
                        spec:
                          namespace: "{namespace}"
                          releaseName: "{release_name}"
          variables:
            - name: PARENT_PIPELINE_URL
              type: String
              value: "{parent_pipeline_url}"
```
#### Jenkins examples:
```yaml
acceptance-tests:
  service: jenkins
  endpoint: Run_Independent_Acceptance_Tests_Job
  variables:
    VERSION_REF: "{version}"
    DATAROBOT_URL: "{end_user_uri}"
    DATAROBOT_API_TOKEN: "{app_admin_api_key}"
    DATAROBOT_USERNAME: "{app_admin_username}"
```


### `performance-tests`

> Version 2.0

> *Optional*

A dictionary that defines performance pipeline (preferably Shrink) to run against a
installed platform to validate the software is working correctly per
[PBMP-5670](https://docs.google.com/document/d/1uU_POHMTVFrcVVjO8y30ean0Gk93TUuU7ya-vRkwGkw/edit).
Each pipeline is defined in terms of these parameters. All values in
these parameters are variable-expanded (see [Variables](#Variables)).

* `host` - The service host to use to kick off the job
* `service` - The type of service to use to run the job (e.g. `shrink`, `jenkins`, `harness`, or `POST`)
* `endpoint` - The job endpoint
    * `mbtest` or `cicada` for `shrink`
    * `<job-name>` for `jenkins`
    * `<organization-name>/projects/<project-name>/pipelines/<pipeline-name>` for `harness`
    * Any arbitary path for `POST`
needed for cost allocation
* `variables` - A dictionary of additional variables to pass to the endpoint


## Variables

Variables are not included in the document, but they are provided as
input and referancable within RELEASE.yaml

Variables in many input fields are substituted. A variable is in
Python `format` syntax (e.g. `foo {bar}` which substitutes the
contents of the variable `bar` into the part of the string containing
`{bar}`.

Optionally, a vertical-bar, `|` can be used to separate a variable name from
a default value. This is most useful in the case of auto-generated parameters
such as `pins_*` and `__*` as described below.

### [empty string]

> Version: 1.0 ONLY

Identical to `version`. This is written as `{}`.

### `version`

> Version: 2.0

Identical to `{major_version}`.`{minor_version}`

### `major_version`

> Version: 2.0
The current major version number (e.g. `9` from `9.1`).

### `minor_version`

> Version: 2.0
The current minor version number (e.g. `1` from `9.1`).

### `repo`

> Version: 2.0
The repository name being branched.

### `other_repo_version`

> Version: 1.0 ONLY

A one-off secondary repository version to update.

### `date`

> Version: 2.0
The current date in ISO format (e.g. `2023-01-01`)

### `end_user_uri`

> Version: 2.0
> Only as a variable of `acceptance-tests`

The URI of the cluster. By default, HTTPS and 443 are assumed, if scheme and
port are not specified.

### `app_admin_api_key`

> Version: 2.0
> Only as a variable of `acceptance-tests`

The admin API key for the app running on the cluster for acceptance tests.

### `app_admin_username`

> Version: 2.0
> Only as a variable of `acceptance-tests`

The app admin username.

### `parent_pipeline_url`

> Version: 2.0
> Only as a variable of `acceptance-tests`

The self-url of the release pipeline executing the acceptance tests. This has no real effect on tests and it's
only used for UX purposes, to keep the acceptance test -> parent release pipeline traceability, so it's highly
recommended to add it to your pipeline.

### `pins_*`

> Version 2.0

All of the data from this config that is stored under the `pins` entry can be used as
variable substitution values. If there is an entry like so:

```YAML
pins:
  - file: VERSION
    value: {version}
```

Then you could use the variable, `pins_0_value`, to reference the `value` key of the first
(0th) entry in `pins`.

### `__*`

> Version 2.0

When the branch command is run, additional parameters can be specified, either via the
command-line or an environment variable. These additional parameters are available
using the prefix `__`, with the following transformations:

* Dashes (`-`) are replaced with underscores (`_`)
* All letters are upcased.

For example, if the command used `--extra-parameters` for this purpose then this command-line:

```
$ branch --extra-parameters='thing-1=5,thing-2=6'
```

Then using the following in your config:

```YAML
pins:
  - file: VERSION
    value: {__THING_1}
```

would substitute in the value `5`.

**IMPORTANT**: If a parameter is referenced, but not provided, an error will be thrown. No
error is thrown if a default value is provided in the config (e.g. `{__THING_1|0}`).

## Examples

### Version 1.0

```YAML
---

description: |
  This is the example repository.
  It contains examples that relate to specific releases.

artifact_build_job: path/to/job/a
artifact_build_job_type: jenkins-jobs

artifact_build_parameters: {}

additional jobs to be updated:
  - path/to/job/b
  - path/to/job/c

master-pins:
  - file: ./VERSION
    command: echo "{version}.0" > ./VERSION

pins:
  - file: ./build.sh
    command: sed -i s/--version master/--version {version}/ ./build.sh

dependencies:
  - name: other-repo
    command: echo "{other_repo_version}" > deps/OTHER_REPO_VERSION
```

### Version 2.0

```YAML
---

description: |
  This is the example repository.
  It contains examples that relate to specific releases.

pins:
  - file: project/Versioning.scala
    command: "sed -i s/master-dev/{version}/"

  - file: python/VERSION
    value: "{version}"

post_branch_cut_jobs:
  - endpoint: /path/to/job
    host: https://jenkins.example.com
    service: jenkins
    variables:
      version: "{version}"
      branch: "release/{version}"
      branchpoint_tag: "release/{version}-branchpoint"

acceptance-tests:
  - endpoint: /path/to/job
    host: https://jenkins.example.com
    service: jenkins
    variables:
      api_url: "{end_user_uri}"
      api_key: "{app_admin_api_key}"
      sha: "release/{version}"
      dr_username: "{app_admin_username}"
      parent_pipeline_url: "{parent_pipeline_url}"

performance-tests:
  - host: http://locust.example.com
    service: shrink
    endpoint: mbtest
    variables:
      description: "MB RELEASE.yaml {version} test"
      predefined_dataset: variety_coverage.yaml

  - host: http://locust.example.com
    service: shrink
    endpoint: cicada
    variables:
      description: "Cicada RELEASE.yaml {version} test"
      test_options:
        cicada_sha: "origin/release/{version}"
        suit_name: webserver_test.py
      cluster_options:
        launch_type: aws
        artifact:
          artifact_type: new
          datarobot_branch: origin/master
        options:
          platform: dockerized
```
