# Third-party inputs

The frozen inputs include third-party software and data. Each component retains its upstream copyright and licence.

| Input | Origin |
| --- | --- |
| Ten npm libraries and their dependency trees | Published npm releases and the package-specific manifests under `datasets/manifests/` |
| Fifty downstream workloads and test providers | The [Stubbifier artifact](https://doi.org/10.5281/zenodo.5599914) (CC BY 4.0 at the record level), with the retained test harnesses and upstream notices |
| GraalVM and NodeProf | Oracle GraalVM Community distributions and the NodeProf project, with the frozen builds used by the experiment apparatus |
| CodeQL CLI and JavaScript library | [CodeQL CLI 2.3.4](https://github.com/github/codeql-cli-binaries/releases/tag/v2.3.4) obtained from GitHub under its [terms](https://github.com/github/codeql-cli-binaries/blob/v2.3.4/LICENSE.md), with library 1.26.0 and the retained Stubbifier module-resolution query |
| SunSpider and edge labels | WebKit SunSpider and the StaticJSCallGraphs research artifact |
| Multi-file static subjects | Retained source trees for debug, express, jshint, request, passport and doctrine |

`manifest/inputs.json` identifies the exact archives. Licence files and notices travel with their upstream trees wherever present in the acquisition.

