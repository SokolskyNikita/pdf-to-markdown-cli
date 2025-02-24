![](_page_47_Figure_1.jpeg)

A connected algebraic set with two irreducible components.

COROLLARY 2.32. The radical of an ideal  $\mathfrak{a}$  in  $k[X\_1, ..., X\_n]$  is a finite intersection of prime ideals,  $\text{rad}(\mathfrak{a}) = \mathfrak{p}\_1 \cap ... \cap \mathfrak{p}\_n$ . If there are no inclusions among the  $\mathfrak{p}\_i$ , then the  $\mathfrak{p}\_i$  are uniquely determined up to order (and they are exactly the minimal prime ideals containing .

PROOF. Write  $V(\mathfrak{a})$  as a union of its irreducible components,  $V(\mathfrak{a}) = \bigcup\_{i=1}^{n} V\_i$ , and let  $\mathfrak{p}\_i = I(V\_i)$ . Then  $\text{rad}(\mathfrak{a}) = \mathfrak{p}\_1 \cap ... \cap \mathfrak{p}\_n$  because they are both radical ideals and

$$V(\text{rad}(\mathfrak{a})) = V(\mathfrak{a}) = \bigcup V(\mathfrak{p}\_i) \stackrel{2.10b}{=} V(\bigcap\_i \mathfrak{p}).$$

The uniqueness similarly follows from the proposition.

## Remarks

An irreducible topological space is connected, but a connected topological space need not be irreducible. For example, the union of two surfaces in 3-space intersecting along a curve is reducible, but connected.

2.33. An algebraic subset  $V$  of  $\mathbb{A}^n$  is disconnected if and only if there exist radical ideals  $\mathfrak{a}$  and  $\mathfrak{b}$  such that  $V$  is the disjoint union of  $V(\mathfrak{a})$  and  $V(\mathfrak{b})$ , so

$$\begin{cases} V = V(\mathfrak{a}) \cup V(\mathfrak{b}) = V(\mathfrak{a} \cap \mathfrak{b}) & \Longleftrightarrow \mathfrak{a} \cap \mathfrak{b} = I(V) \\\emptyset = V(\mathfrak{a}) \cap V(\mathfrak{b}) = V(\mathfrak{a} + \mathfrak{b}) & \Longleftrightarrow \mathfrak{a} + \mathfrak{b} = k[X\_1, \dots, X\_n]. \end{cases}$$

Then

$$k[V] \simeq \frac{k[X\_1, \ldots, X\_n]}{\mathfrak{a}} \times \frac{k[X\_1, \ldots, X\_n]}{\mathfrak{b}}$$

by Theorem 1.1.

2.34. A Hausdorff space is noetherian if and only if it is finite, in which case its irreducible components are the one-point sets.

2.35. In  $k[X\_1, ..., X\_n]$ , a principal ideal  $(f)$  is radical if and only if  $f$  is square-free, in which case  $f$  is a product of distinct irreducible polynomials,  $f = f\_1 ... f\_r$ , and  $(f) = (f\_1) \cap ... \cap (f\_r)$ .