# Docs http://docs.fabfile.org/
from fabric.api import *
from fabric.contrib.files import *
# Requires https://github.com/ilogue/fexpect
from ilogue.fexpect import expect, expecting, run as erun, sudo as esudo

# This assuming yum based repositories (CentOS)
# TODO
#  - Generalize to use either apt or yum
#  - Add rsync -aAXvz /* user@hostname:/some/dir --exclude={/dev/*,/proc/*,/sys/*,/tmp/*,/run/*,/mnt/*,/media/*,/lost+found}

if not os.path.exists('settings.py'):
    print 'initializing settings file...'
    print
    baseSettings = """from fabric.api import *
env.user = root
env.hosts = ['127.0.0.1']

# This can be used to decorate functions, not used right now
#env.roledefs = {
#    'initial-setup': ['root@127.0.0.1',],
#    'otherwise': ['127.0.0.1'],
#}"""
    local('echo "%s" > settings.py' % baseSettings)
    print
    print 'You should fill out the server settings in settings.py'
    exit(0)
else:
    import settings as ssettings

# Don't have to set env.user use ~/.fabricrc
# And set user = your_ssh_user_name
# Or you can run setup_env_user and answer the questions
#env.user = 'someuser'

def haveRC():
    return os.path.exists(env.rcfile)

# Decorator for checking ssh user name and other things
def runChecks(func):
    def check(*args, **kargs):
        if not os.path.exists('settings.py'):
            pass
        # Ignore this stuff for now
        #elif not haveRC():
        #    print 'Please run setup_env_user to setup ssh username'
        #    exit(0)
        #elif not 'user =' in open('{rc}'.format(rc=env.rcfile)).read():
            #print 'Please run setup_env_user to setup ssh username'
            #exit(0)
        return func(*args, **kargs)
    return check

# Local info
def localInfo():
    local('uname -a')

# Setup Environment User
def setup_env_user():
    name = prompt('Please input your ssh username for the remote system: ')
    if not haveRC():
        local('touch {rc}'.format(rc=env.rcfile))
    if 'user =' in open('{rc}'.format(rc=env.rcfile)).read():
        local('sed -i \'s/^user.*=.*$/user = {username}/g\' {rc}'.format(username=name, rc=env.rcfile))
    else:
        local('echo "user = {username}" >> {rc}'.format(username=name, rc=env.rcfile))

# Use sudo
def useSudo():
    if env.user != "root":
        return True
    else:
        return False
    
# Helper to do as sudo once root has been changed and can no longer ssh in
def runcmd(arg):
    if useSudo():
        return sudo("%s" % arg, pty=True)
    else:
        return run("%s" % arg, pty=True)
        
# Extension fexpect helper
def eruncmd(arg):
    if useSudo():
        return esudo("%s" % arg)
    else:
        return erun("%s" % arg)
        
# Sed line prepend append
def insert_line_before(pattern, string, where):
    runcmd('sed -i \'/{search}/ i\{content}\' {filename}'.format(search=pattern, content=string, filename=where))

def insert_line_after(pattern, string, where):
    runcmd('sed -i \'/{search}/ a\{content}\' {filename}'.format(search=pattern, content=string, filename=where))
    
# Check if package installed
def check_package_installed(package_name):
    with settings(hide('stderr','stdout', 'warnings'),warn_only=True):
        out = runcmd('yum list installed {pkg}'.format(pkg=package_name))
        if 'Error: No matching Packages to list' in out:
            print 'Package %s is not installed' % package_name
            return False
        else:
            print 'Package %s is installed' % package_name
            return True

# Fix arguments since they are passed as string
def stringToBool(arg):
    if arg == True or arg == 'y' or arg == 'Y' or arg == 'True' or arg == 'true':
        return True
    elif arg == False or arg == 'n' or arg == 'N' or arg == 'False' or arg == 'false':
        return False
    else:
        print 'Argument expected is either y/Y/True/true or n/N/False/false'
        exit(0)

######################## Server Calls #########################

# test
@runChecks
def uname():
    runcmd('uname -a')

@runChecks
def add_user(username, password, resetpasswd, groups='', sshd='sshd'):
    usercmd = 'adduser {name}'.format(name=username)
    resetpasswd = stringToBool(resetpasswd)
    if groups:
        usercmd += ' -G ' + groups
    runcmd(usercmd)
    runcmd('echo "{name}:{password}" | chpasswd'.format(name=username, password=password))
    if resetpasswd == True:
        runcmd('chage -d 0 {name}'.format(name=username))
    # Add to ssh
    sed('/etc/ssh/sshd_config', 'AllowUsers (.*)$', 'AllowUsers \\1 {name}'.format(name=username), '', useSudo())
    runcmd('/etc/init.d/{0}'.format(sshd) + ' restart')

@runChecks
def enable_root_ssh(enable):
    if stringToBool(enable) == True:
        sed('/etc/ssh/sshd_config', '^(#)PermitRootLogin\ yes', 'PermitRootLogin\ yes', '', useSudo())
    elif 'n':
        sed('/etc/ssh/sshd_config', '^(#)PermitRootLogin\ yes', 'PermitRootLogin\ no', '', useSudo())
    
@runChecks
def add_vhost(userdir, servername):
    # check if userdir exists
    if not exists('/home/{user}'.format(user=userdir)):
        print 'User directory doesn\'t exist'
        return
    if not check_package_installed('httpd'):
        print 'Install apache first'
        return
    entry="""
    
<VirtualHost *:80>
        DocumentRoot /home/{directory}/www
        ServerName {server}
        DirectoryIndex index.php
        ErrorLog /home/{directory}/www-log
        CustomLog /home/{directory}/www-access common
        <Directory "/home/{directory}/www">
               AllowOverride All
               Allow from All
        </Directory>
</VirtualHost>""".format(directory=userdir, server=servername)
    runcmd('echo "{content}" >> /etc/httpd/conf.d/{server}.conf'.format(content=entry, server=servername))
    runcmd('mkdir -p /home/{user}/www'.format(user=userdir))
    if not exists('/home/{user}/www/index.php'.format(user=userdir)):
        runcmd('echo "Hi from {0} webserver on port 80." > /home/{0}/www/index.php'.format(userdir))
    runcmd('chown -R {user}:{user} /home/{user}/www'.format(user=userdir))
    runcmd('chmod -R 755 /home/{user}/www'.format(user=userdir))
    runcmd('chcon -R system_u:object_r:httpd_sys_content_t:s0 /home/{user}'.format(user=userdir))
    runcmd('service httpd restart')
    
    
@runChecks
def generate_vhost_ssl_cert(servername, password):
    # Create self-signed certificates
    runcmd('mkdir -p ~/cert-temp')
    with cd('~/cert-temp'):
        # generate private key
        privatekey = []
        privatekey += expect('Enter pass phrase for server.key:', password)
        privatekey += expect('Verifying - Enter pass phrase for server.key:', password)

        with expecting(privatekey):
            eruncmd('openssl genrsa -des3 -out server.key 2048')
            
        csr = []
        csr += expect('Enter pass phrase for server.key:', password)
        csr += expect('Country Name \(2 letter code\) \[.*\]:', 'US')
        csr += expect('State or Province Name \(full name\) \[.*\]:', 'Florida')
        csr += expect('Locality Name \(eg, city\) \[.*\]:', 'Miami')
        csr += expect('Organization Name \(eg, company\)', 'Miami')
        csr += expect('Organizational Unit Name \(eg, section\) \[\]:', 'Miami')
        csr += expect('Common Name', servername);
        csr += expect('Email Address \[\]:', 'noreply@noemail.com')
        csr += expect('A challenge password \[\]:', password)
        csr += expect('An optional company name \[\]:', '')
        
        with expecting(csr):
            eruncmd('openssl req -new -key server.key -out server.csr')
            
        runcmd('cp server.key server.key.org')
        
        serverkey = []
        serverkey += expect('Enter pass phrase', password)
        
        with expecting(serverkey):
            eruncmd('openssl rsa -in server.key.org -out server.key')
            
        runcmd('openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt')
        
        if not exists('/etc/httpd/ssl'):
            runcmd('mkdir -p /etc/httpd/ssl')
        runcmd('cp server.crt /etc/httpd/ssl/{server}.crt'.format(server=servername))
        runcmd('cp server.key /etc/httpd/ssl/{server}.key'.format(server=servername))
    runcmd('rm -fr ~/cert-temp')

@runChecks
def add_vhost_ssl(userdir, servername, password):
    # check if userdir exists
    if not exists('/home/{user}'.format(user=userdir)):
        print 'User directory doesn\'t exist'
        return
    if not check_package_installed('httpd'):
        print 'Install apache first'
        return
    if not check_package_installed('mod_ssl'):
        print 'Install mod_ssl first'
        return
    if not check_package_installed('openssl'):
        print 'Install openssl first'
        return
    entry="""
    
<VirtualHost *:443>
        SSLEngine on
        SSLProtocol all -SSLv2
        SSLCipherSuite ALL:!ADH:!EXPORT:!SSLV2:RC4+RSA:+HIGH:+MEDIUM:+LOW
        SSLCertificateFile /etc/httpd/ssl/{server}.crt
        SSLCertificateKeyFile /etc/httpd/ssl/{server}.key
        SetEnvIf User-Agent ".*MSIE.*" nokeepalive ssl-unclean-shutdown
        DocumentRoot /home/{directory}/wwws
        ServerName {server}
        DirectoryIndex index.php
        ErrorLog /home/{directory}/www-log-ssl
        CustomLog /home/{directory}/www-access-ssl common
        <Directory "/home/{directory}/wwws">
               AllowOverride All
               Allow from All
        </Directory>
</VirtualHost>""".format(directory=userdir, server=servername)
    
    # Add ssl entry
    runcmd('echo "{content}" >> /etc/httpd/conf.d/{server}.conf'.format(content=entry, server=servername))
    
    # Create self-signed certificates
    generate_vhost_ssl_cert(servername, password)
    
    runcmd('mkdir -p /home/{user}/wwws'.format(user=userdir))
    if not exists('/home/{user}/wwws/index.php'.format(user=userdir)):
        runcmd('echo "Hi from {0} webserver on port 443." >> /home/{0}/wwws/index.php'.format(userdir))
    runcmd('chown -R {user}:{user} /home/{user}/wwws'.format(user=userdir))
    runcmd('chmod -R 755 /home/{user}/wwws'.format(user=userdir))
    runcmd('chcon -R system_u:object_r:httpd_sys_content_t:s0 /home/{user}'.format(user=userdir))
    runcmd('service httpd restart')

@runChecks
def install_lamp(update=True):
    if stringToBool(update) == True:
        # update
        runcmd('yum -y update')
    # Apache / PHP / 
    app_list = ['httpd',
                'mod_ssl',
                'openssl',
                'unixODBC',
                'php',
                'php-pear',
                'php-bcmath',
                'php-cli',
                'php-common',
                'php-dba',
                'php-devel',
                'php-gd',
                'php-imap',
                'php-intl',
                'php-ldap',
                'php-mbstring',
                'php-mysql',
                'php-odbc',
                'php-pdo',
                'php-pgsql',
                'php-process',
                'php-pspell',
                'php-snmp',
                'php-soap',
                'php-xml',
                'php-xmlrpc',
                'freetds']
    runcmd('yum -y install ' + ' '.join(map(str, app_list)))
    runcmd('chkconfig --levels 235 httpd on')
    
    # Add iptables for port 80 and 443
    insert_line_before('^-A INPUT.*icmp-host-prohibited', '-A INPUT -p tcp -m tcp --dport 80 -j ACCEPT', '/root/default.iptables')
    insert_line_before('^-A INPUT.*icmp-host-prohibited', '-A INPUT -p tcp -m tcp --dport 443 -j ACCEPT', '/root/default.iptables')
    insert_line_before('^-A INPUT.*icmp-host-prohibited', '-A OUTPUT -p tcp -m tcp --sport 80 -j ACCEPT', '/root/default.iptables')
    insert_line_before('^-A INPUT.*icmp-host-prohibited', '-A OUTPUT -p tcp -m tcp --sport 443 -j ACCEPT', '/root/default.iptables')
    runcmd('iptables-restore /root/default.iptables')
    runcmd('/etc/init.d/iptables save')
    runcmd('service iptables restart')
    
    # Add virtual host name for ssl so _default_ doesn't take precedence
    append('/etc/httpd/conf.d/ssl.conf', 'NameVirtualHost *:443', useSudo())
    
    # Start apache
    runcmd('service httpd start')

# Setup MySql
@runChecks
def install_mysql(password):
    if not check_package_installed('mysql-server'):
        runcmd('yum -y update')
        runcmd('yum -y install mysql-server')
    runcmd('chkconfig --levels 235 mysqld on')
    runcmd('service start mysqld')
    # Secure mysql
    setup = []
    setup += expect('Enter current password for root (enter for none):','')
    setup += expect('Set root password? \[Y/n\]','y')
    setup += expect('New password:', password)
    setup += expect('Re-enter new password:', password)
    setup += expect('Remove anonymous users? \[Y/n\]', 'y')
    setup += expect('Disallow root login remotely? \[Y/n\]', 'y')
    setup += expect('Remove test database and access to it? \[Y/n\]', 'y')
    setup += expect('Reload privilege tables now? \[Y/n\]', 'y')

    with expecting(setup):
        eruncmd('mysql_secure_installation')
    

# Setup git (Operates over ssh so no need to modify iptables)
@runChecks
def install_git():
    if not check_package_installed('git'):
        runcmd('yum -y install git')
    
    if not exists('/home/git'):
        append('/etc/shells', '/usr/bin/git-shell', useSudo())
        runcmd('adduser -s /usr/bin/git-shell git')
        runcmd('mkdir /home/git/.ssh')
        runcmd('touch /home/git/.ssh/authorized_keys')
        runcmd('chmod 700 /home/git/.ssh')
        runcmd('chmod 600 /home/git/.ssh/authorized_keys')
        runcmd('chown -R git:git /home/git/.ssh')
        # Create the repository home
        runcmd('mkdir /opt/git')
        runcmd('chown -R git:git /opt/git')

# create git repository
@runChecks
def create_git_repository(name):
    if not exists('/home/git'):
        print 'Gitorius must be installed first before trying to add repositories'
        return
    runcmd('mkdir /opt/git/{repo}.git'.format(repo=name))
    with cd('/opt/git/{repo}.git'.format(repo=name)):
        runcmd('git --bare init')
    runcmd('chown -R git:git /opt/git/{repo}.git'.format(repo=name))

# Create ssl keys for current computer and append to git so that you may commit changes
@runChecks
def create_git_keys():
    if not check_package_installed('git'):
        print 'Gitorius must be installed first before trying to add ssh keys'
        return
    
    local('ssh-keygen -t dsa')
    put('~/.ssh/id_dsa.pub', '/root/git_ssh_temp_key', useSudo())
    runcmd('cat /root/git_ssh_temp_key >> /home/git/.ssh/authorized_keys')
    runcmd('rm -fr /root/git_ssh_temp_key')

# Setup SVN
@runChecks
def install_svn():
    if not check_package_installed('subversion'):
        runcmd('yum -y install subversion')

# Install java
@runChecks
def install_java(platform='64', version='1.8'):
    def grabPackage(version, filename):
        location = ''
        cmd = 'wget --no-check-certificate --no-cookies --header "Cookie: gpw_e24=http%3A%2F%2Fwww.oracle.com%2F; oraclelicense=accept-securebackup-cookie"'
        if '1.6' in version:
            location = 'http://download.oracle.com/otn-pub/java/jdk/6u45-b06/'
        elif '1.7' in version:
            location = 'http://download.oracle.com/otn-pub/java/jdk/7u21-b11/'
        else:
            location = 'http://download.oracle.com/otn-pub/java/jdk/8u45-b14/'
        runcmd('{0} "{1}{2}"'.format(cmd, location, filename))
    def setAlternatives(version, release):
        commands = [['jre/', 'java'], ['', 'jar'], ['','javac'], ['','javaws']]
        for command in commands:
            runcmd('alternatives --install /usr/bin/{0} {0} /usr/java/jdk{1}.0_{2}/{3}bin/{0} 20000'.format(command[1], version, release, command[0]))
            runcmd('alternatives --set {0} /usr/java/jdk{1}.0_{2}/{3}bin/{0}'.format(command[1], version, release, command[0]))
    
    def setEnvironment(version, release):
        append('/etc/profile', 'export JAVA_HOME=/usr/java/jdk{0}.0_{1}'.format(version, release), useSudo())
        append('/etc/profile', 'export JRE_HOME=$JAVA_HOME/jre'.format(version, release), useSudo())
        append('/etc/profile', 'export PATH=$PATH:$JAVA_HOME/bin:$JRE_HOME/bin', useSudo())
    
    if version == '1.6':
        #jdk and jre
        packages = []
        if platform == '32':
            packages = ['jdk-6u45-linux-i586-rpm.bin', 'jre-6u45-linux-i586-rpm.bin']
        elif packages == '64':
            packages = ['jdk-6u45-linux-x64-rpm.bin', 'jre-6u45-linux-x64-rpm.bin']
        else:
            print 'Platform is either 32 or 64'
            exit(0)
        for package in packages:
            runcmd('mkdir -p java-temp')
            with cd('java-temp'):
                grabPackage(version, package)
                runcmd('chmod +x %s' % package)
                runcmd('./%s' % package)
            runcmd('rm -fr java-temp')
        # alternatives
        setAlternatives('1.6', '45')
        # Environment
        setEnvironment('1.6', '45')
    elif version == '1.7':
        packages = []
        if platform == '32':
            packages = ['jdk-7u79-linux-i586.rpm', 'jre-7u79-linux-i586.rpm']
        elif platform == '64':
            packages = ['jdk-7u79-linux-x64.rpm', 'jre-7u79-linux-x64.rpm']
        else:
            print 'Platform is either 32 or 64'
            exit(0)
        for package in packages:
            runcmd('mkdir -p java-temp')
            with cd('java-temp'):
                grabPackage(version, package)
                runcmd('rpm -Uvh %s' % package)
            runcmd('rm -fr java-temp')
        # alternatives
        setAlternatives('1.7', '79')
        # Environment
        setEnvironment('1.7', '79')
    elif version == '1.8':
        packages = []
        if platform == '32':
            packages = ['jdk-8u45-linux-i586.tar.gz']
        elif platform == '64':
            packages = ['jdk-8u45-linux-x64.tar.gz']
        else:
            print 'Platform is either 32 or 64'
            exit(0)
        for package in packages:
            runcmd('mkdir -p java-temp')
            with cd('java-temp'):
                grabPackage(version, package)
                #runcmd('rpm -Uvh %s' % package)
                runcmd('tar xvzf {0}'.format(package))
                runcmd('mkdir -p /usr/java')
                runcmd('mv jdk{0}.0_{1} /usr/java'.format(version, '45'))
            runcmd('rm -fr java-temp')
        # alternatives
        setAlternatives('1.8', '45')
        # Environment
        setEnvironment('1.8', '45')
    else:
        print 'Version is either 1.6, 1.7 or 1.8'
        exit(0)

# Install hadoop
@runChecks
def install_hadoop(platform='64', version='1.8'):
    # install java 7
    install_java(platform, version)
    runcmd('mkdir -p hadoop')
    with cd('hadoop'):
        hadoop = 'hadoop-1.1.2'
        url = 'http://mirrors.ibiblio.org/apache/hadoop/common/stable/'
        runcmd('wget ' + url + hadoop + '-bin.tar.gz')
        runcmd('tar xvzf ' + hadoop + '-bin.tar.gz')
        runcmd('mv ' + hadoop + ' /opt/hadoop')
    runcmd('rm -fr hadoop')
    add_user('hadoop', 'hdevel', 'n')
    runcmd('chown hadoop:hadoop /opt/hadoop')
    append('/etc/profile', 'export HADOOP_OPTS=-Djava.net.preferIPv4Stack=true')
    append('/etc/profile', 'export HADOOP_HOME=/opt/hadoop')
    append('/etc/profile', 'export HADOOP=$HADOOP_HOME/bin/hadoop')
    append('/etc/profile', 'export PATH=$PATH:$HADOOP_HOME/bin')
    
# Install Kerberos
@runChecks
def install_kerberos(ad_controller, ad_domain):
    # update
    runcmd('yum -y update')
    # Basic applications
    app_list = ['authconfig',
                'pam_krb5',
                'fprintd-pam']
    runcmd('yum -y install ' + ' '.join(map(str, app_list)))
    # Reference http://www.server-world.info/en/note?os=CentOS_6&p=krb
    runcmd('authconfig --enablekrb5 --krb5kdc=' + ad_controller + ' --krb5realm=' + ad_domain.upper() + " --updateall")
    
# Add kerberos user
@runChecks
def add_kerberos_user(username, groups=''):
    usercmd = 'adduser {name}'.format(name=username)
    if groups:
        usercmd += ' -G ' + groups
    runcmd(usercmd)
    # Add to ssh
    sed('/etc/ssh/sshd_config', 'AllowUsers (.*)$', 'AllowUsers \\1 {name}'.format(name=username), '', useSudo())
    runcmd('/etc/init.d/sshd restart')

# Change Default Keyboard
@runChecks
def change_keyboard(keyboard):
    sed('/etc/sysconfig/keyboard', 'KEYTABLE=".*"', 'KEYTABLE="{kbd}"'.format(kbd=keyboard), '', useSudo())
    reboot()

# Reboot system
@runChecks
def reboot():
    runcmd('reboot')

# Initialize the box
@runChecks
def initialize_box():
    # update
    runcmd('yum -y update')
    # Basic applications
    app_list = ['wget',
                'sudo',
                'postfix',
                'nano',
                'vim',
                'vim-common',
                'vim-enhanced',
                'vim-minimal',
                'perl',
                'python',
                'kernel-headers',
                'make',
                'gcc',
                'ntp']
    runcmd('yum -y install ' + ' '.join(map(str, app_list)))

    # Setup sudoers to wheel
    uncomment('/etc/sudoers', '^# %wheel.\s*ALL=\(ALL\).\s*ALL', useSudo())
    
    # Dump iptables
    runcmd('iptables-save > /root/default.iptables')
    
    # Append vi to profile
    append('/etc/profile', 'alias vi="vim"', useSudo())
    
    lines = """
# Users
AllowUsers root"""
    runcmd('echo "{content}" >> /etc/ssh/sshd_config'.format(content=lines))
    # Do not disable this unless you want a less secure box -miguel
    #runcmd('sed -i \'s/GSSAPIAuthentication\ yes/GSSAPIAuthentication\ no/g\' /etc/ssh/sshd_config')
    
    # NTP
    runcmd('chkconfig ntpd on')
    runcmd('ntpdate pool.ntp.org')
    
    # reboot
    reboot()



#################### RESOURCES ######################################
# Centos stuff
# minimal - http://superuser.com/questions/365118/how-can-i-install-centos-6-without-the-gui
# minimal - http://www.chriscolotti.us/technology/how-to-get-started-with-centos-minimal/
# lamp - http://duskonit.blogspot.com/2011/10/howto-install-centos-6-as-production.html
# lamp - http://library.linode.com/lamp-guides/centos-6

# Others
# git - http://git-scm.com/book/en/Git-on-the-Server-Setting-Up-the-Server
# git - http://erikwebb.net/blog/setup-simple-ssh-based-git-hosting
# ssh keys - http://paulkeck.com/ssh/
