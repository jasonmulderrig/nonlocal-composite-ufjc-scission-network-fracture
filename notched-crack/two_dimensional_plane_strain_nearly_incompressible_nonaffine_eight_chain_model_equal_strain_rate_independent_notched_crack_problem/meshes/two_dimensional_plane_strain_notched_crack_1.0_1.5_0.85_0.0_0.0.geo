
Mesh.Algorithm = 8;
coarse_mesh_elem_size = DefineNumber[ 0.01, Name "Parameters/coarse_mesh_elem_size" ];
x_notch_point = DefineNumber[ 0.85, Name "Parameters/x_notch_point" ];
r_notch = DefineNumber[ 0.02, Name "Parameters/r_notch" ];
L = DefineNumber[ 1, Name "Parameters/L"];
H = DefineNumber[ 1.5, Name "Parameters/H"];
Point(1) = {0, 0, 0, coarse_mesh_elem_size};
Point(2) = {x_notch_point-r_notch, 0, 0, coarse_mesh_elem_size};
Point(3) = {0, -r_notch, 0, coarse_mesh_elem_size};
Point(4) = {0, -H/2, 0, coarse_mesh_elem_size};
Point(5) = {L, -H/2, 0, coarse_mesh_elem_size};
Point(6) = {L, H/2, 0, coarse_mesh_elem_size};
Point(7) = {0, H/2, 0, coarse_mesh_elem_size};
Point(8) = {0, r_notch, 0, coarse_mesh_elem_size};
Point(9) = {x_notch_point-r_notch, r_notch, 0, coarse_mesh_elem_size};
Point(10) = {x_notch_point, 0, 0, coarse_mesh_elem_size};
Point(11) = {x_notch_point-r_notch, -r_notch, 0, coarse_mesh_elem_size};
Line(1) = {11, 3};
Line(2) = {3, 4};
Line(3) = {4, 5};
Line(4) = {5, 6};
Line(5) = {6, 7};
Line(6) = {7, 8};
Line(7) = {8, 9};
Circle(8) = {9, 2, 10};
Circle(9) = {10, 2, 11};
Curve Loop(21) = {1, 2, 3, 4, 5, 6, 7, 8, 9};
Plane Surface(31) = {21};
Mesh.MshFileVersion = 2.0;
