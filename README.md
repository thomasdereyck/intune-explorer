# intune-explorer
A tool that displays a convenient summary of Intune related objects assigned to an Azure AD group.

## Requirements
- Python 3, from python.org.
- requests module. Install as root/administrator with the following command: "pip install requests".
- An app registration in Azure AD with the following permissions set up:
  - DeviceManagementApps.Read.All
  - DeviceManagementConfiguration.Read.All
  - DeviceManagementManagedDevices.Read.All
  - DeviceManagementServiceConfig.Read.All
  - Group.Read.All

## Configuration
Before executing the script, edit the script and fill out the variables in the configuration section.
