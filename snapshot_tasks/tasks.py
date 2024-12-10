from cumulusci.core.tasks import BaseSalesforceTask
from datetime import datetime
import subprocess
import json
import time

class SnapshotOrg(BaseSalesforceTask):
    task_options = {
        "snapshot_name": {
            "description": "Name to give the snapshot (max 15 characters)",
            "required": False,
        },
        "wait": {
            "description": "Number of seconds to wait for completion (default: 0 = wait indefinitely)",
            "required": False,
            "default": 0,
        }
    }

    def _init_options(self, kwargs):
        super()._init_options(kwargs)
        if not self.options.get("snapshot_name"):
            date_stamp = datetime.now().strftime("%m%dt%H%M")
            self.options["snapshot_name"] = f"dev{date_stamp}"

    def _run_task(self):
        username = self.org_config.username
        snapshot_name = self.options["snapshot_name"]
        wait_time = int(self.options.get("wait", 60))

        if len(snapshot_name) > 15:
            raise ValueError(f"Snapshot name '{snapshot_name}' exceeds 15 character limit")

        self.logger.info(f"Creating snapshot '{snapshot_name}' from org: {username}")
        
        command = f"sf org snapshot create -o {username} -n {snapshot_name} --json"
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                capture_output=True,
                text=True
            )
            
            response = json.loads(result.stdout)
            snapshot_data = response['result']
            
            # Log clean formatted output
            self.logger.info("Snapshot created successfully:")
            self.logger.info(f"  ID: {snapshot_data['Id']}")
            self.logger.info(f"  Name: {snapshot_data['SnapshotName']}")
            self.logger.info(f"  Status: {snapshot_data['Status']}")
            self.logger.info(f"  Source Org: {snapshot_data['SourceOrg']}")
            self.logger.info(f"  Created: {snapshot_data['CreatedDate']}")
            
            if response.get('warnings'):
                self.logger.warning("\nWarnings:")
                for warning in response['warnings']:
                    self.logger.warning(f"  {warning}")

            if wait_time >= 0:
                self._wait_for_completion(snapshot_data['SnapshotName'], wait_time)

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating snapshot: {e.stderr}")
            raise

    def _wait_for_completion(self, snapshot_name, timeout):
        # If timeout is 0 or negative, wait indefinitely
        infinite_wait = timeout <= 0
        start_time = time.time()
        check_count = 0
        
        while True:  # Always loop forever
            command = "sf org snapshot list --json"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            try:
                data = json.loads(result.stdout)
                snapshots = data.get('result', [])
                
                # Find our snapshot
                for snapshot in snapshots:
                    if snapshot['SnapshotName'] == snapshot_name:
                        status = snapshot['Status']
                        
                        # Show progress every 30 seconds
                        if check_count % 6 == 0:  # 6 * 5 seconds = 30 seconds
                            self.logger.info(f"Current status: {status}")
                        
                        if status == 'Completed':
                            self.logger.info(f"Snapshot '{snapshot_name}' completed successfully!")
                            return
                        elif status == 'Failed':
                            error = snapshot.get('Error', 'Unknown error')
                            raise Exception(f"Snapshot failed: {error}")
                        
                        break
                
                check_count += 1
                time.sleep(5)
                
            except json.JSONDecodeError:
                self.logger.error("Error parsing snapshot status")
                raise