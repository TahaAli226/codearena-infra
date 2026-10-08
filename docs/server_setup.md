# lab-07 - Server Setup

## Access
- User: `student`
- SSH keys only (root login disabled)

## Setup

### Update and Auto Updates
update the system and ensure automatic security updates (only for repos that label security updates so repos that don't have security labels like docker get updated manually)
```bash
sudo dnf upgrade -y
sudo dnf install -y dnf-automatic
sudo vi /etc/dnf/automatic.conf
```
change the following configs inside the file:
```
upgrade_type = security
download_updates = yes
apply_updates = yes
reboot = never
```

enable the automatic security updates timer and check that it's working
```bash
sudo systemctl enable --now dnf-automatic.timer
systemctl status dnf-automatic.timer   # should be active and a trigger date 
```
reboots are manual, check if one is needed
```bash
sudo dnf needs-restarting -r
```
### sshd
check what sshd is using
```bash
sudo sshd -T | grep -Ei 'passwordauthentication|permitrootlogin|pubkeyauthentication'
```
allow only pubkeyauthentication and disable permitrootlogin and passwordauthentication
(in the case of this server password was off only permitroot and pubkey was active)
we add a file instead of changing the main config to override the config
```bash
sudo vi /etc/ssh/sshd_config.d/00-noroot.conf
```

write the config in the file
00-noroot.conf:
```
PermitRootLogin no
```

test the config and reload then check if it applied
```bash
sudo sshd -t && sudo systemctl reload sshd
sudo sshd -T | grep -i permitroot   # should return permitrootlogin no
```

### SELinux
check if SELinux is active and enforcing
```bash
sestatus   # should be enforcing
```

check if kernel arg turns SELinux off before the file is read
(in this server it came back 0 that means no kernel arg is turning SELinux off if it says otherwise we need to remove the args)
```bash
sudo grubby --info=ALL | grep -c 'selinux=0'  # should return 0
```

in case the check didn't return 0
this command basically removes all selinux args from all kernels installed on the system (SELinux is on by default in RHEL-family kernels)
```bash
sudo grubby --update-kernel ALL --remove-args selinux  # needs a system reboot read below for further instructions
```

in case of applying the command above make sure you set SELinux to permissive and create /.autorelabel so that any files created when selinux was off gets a label and nothing gets blocked after the reboot check if anything would be blocked
if not switch it back to enforcing 
```bash
sudo sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
sudo touch /.autorelabel        # relabels every file in the next boot
sudo reboot
sudo ausearch -m avc -ts boot   # checks if anything would be blocked
sudo setenforce 1               # changes it for this boot only so you don't need to reboot
sudo sed -i 's/^SELINUX=.*/SELINUX=enforcing/' /etc/selinux/config  # changes it for future boots 
```

### Firewall
check if firewalld is active and enabled
```bash
systemctl status firewalld      # should be enabled + active
sudo firewall-cmd --list-all    # to check services allowed through the firewall
```

if firewalld not enabled we make sure ssh is listed then enable it
```bash
sudo firewall-offline-cmd --list-services  # if ssh is listed you're good to enable the firewall 
sudo systemctl enable --now firewalld
```

### Docker 
install docker and docker compose (taken from the official docker RHEL family installation docs)
```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker student  # added to run docker commands without sudo needs logging in and out to apply 
```

### CodeArena_Setup
make the directory  for the app and change the directory owner to the user 
```bash
sudo mkdir -p /opt/code_arena
sudo chown -R student:student /opt/code_arena
```

allow port 8000 through  the firewall 
```bash
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

infra files and the api files were copied to the server manually since auto deploys aren't setup yet 
