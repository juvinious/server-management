execute "apt-get-update" do
  command "apt-get update"
  ignore_failure true 
end

package "scons" do
  action :install
end

package "libsdl1.2-dev" do
  action :install
end

package "libpng12-dev" do
  action :install
end

package "libfreetype6-dev" do
  action :install
end

package "g++" do
  action :install
end

package "zlib1g-dev" do
  action :install
end

package "python-dev" do
  action :install
end 

package "make" do
  action :install
end

package "libogg-dev" do
  action :install
end

package "libvorbis-dev" do
  action :install
end

package "libmpg123-dev" do
  action :install
end

package "subversion" do
  action :install
end

script "co_paintown" do
  interpreter "bash"
  user "vagrant"
  cwd "/home/vagrant"
  code <<-EOH
  svn co svn://svn.code.sf.net/p/paintown/code/trunk paintown
  EOH
end

script "make_paintown" do
  interpreter "bash"
  cwd "/home/vagrant/paintown"
  code <<-EOH
  make static
  EOH
# ln -s /home/vagrant/paintown /vagrant/paintown
end
