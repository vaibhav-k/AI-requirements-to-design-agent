# Icon attribution

The PNG files in this directory are Microsoft's official Azure
Architecture Icons, sourced from the `diagrams` Python package's bundled
icon resources (https://pypi.org/project/diagrams/,
`resources/azure/...` inside the installed package - the package itself
is MIT-licensed; the icon assets are Microsoft's, made available for
building architecture diagrams like the ones this project generates).

Each file was renamed to a short, stable slug (see
`app/design/icons.py`'s `_KEYWORD_ICON_MAP`) so the mapping from
"concept" (kubernetes, database, load balancer, ...) to file doesn't
depend on any single upstream package's internal file layout:

| File                     | Source (relative to `resources/azure/`)     |
| ------------------------ | -------------------------------------------- |
| api-gateway.png          | integration/api-management-services.png     |
| app-service.png          | appservices/app-services.png                |
| blob-storage.png         | storage/blob-storage.png                    |
| cache.png                | general/cache.png                           |
| client.png               | general/browser.png                         |
| container-registry.png   | containers/container-registries.png         |
| container.png            | compute/container-instances.png             |
| cosmos-db.png            | databases/azure-cosmos-db.png               |
| devops-pipeline.png      | devops/pipelines.png                        |
| function.png             | compute/function-apps.png                   |
| generic-external.png     | azure.png (generic Azure logo)              |
| generic-service.png      | general/cubes.png                           |
| identity.png             | identity/azure-active-directory.png         |
| key-vault.png            | security/key-vaults.png                     |
| kubernetes.png           | containers/kubernetes-services.png          |
| load-balancer.png        | networking/load-balancers.png               |
| logic-app.png            | integration/logic-apps.png                  |
| monitor.png              | monitor/monitor.png                         |
| queue.png                | storage/queues-storage.png                  |
| service-bus.png          | integration/azure-service-bus.png           |
| sql-database.png         | databases/sql-database.png                  |
| virtual-machine.png      | compute/virtual-machine.png                 |
| virtual-network.png      | networking/virtual-networks.png             |

If Microsoft's official icon set is updated, or a different/newer
source is preferred, these files can be swapped out individually as
long as the slug (filename) stays the same - `app/design/icons.py`
doesn't know or care where a given slug's PNG originally came from.
